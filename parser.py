import os
import re
import json
import time
import random
import threading
import pandas as pd

from queue import Queue
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


# =========================
# SETTINGS
# =========================

SCROLLS = 3

START_PAGE = 1
END_PAGE = 343

MAX_CARS = 18000

N_WORKERS = 2
RESTART_EVERY = 10

OUTPUT_FILE = "cars.csv"
BACKUP_FILE = "cars_backup.csv"

USD_RATE = 390
EUR_RATE = 1.1


LABELS = {
    "Վազքը": "Mileage",
    "Թափքը": "Body",
    "Շարժիչը": "Fuel",
    "Փոխանցման տուփը": "Gearbox",
    "Ղեկը": "Steering",
    "Գույնը": "Color",
    "Սրահի գույնը": "InteriorColor",
    "Շարժիչի ծավալը": "Engine",
    "Ձիաուժը": "Horsepower",
    "Մխոցների քանակը": "Cylinders",
    "Քարշակը": "Drive",
    "Դռների քանակը": "Doors",
    "Վիճակը": "Condition",
}


TWO_WORD_MAKES = [
    "Rolls Royce",
    "Land Rover",
    "Alfa Romeo",
    "Aston Martin",
    "Great Wall"
]


# =========================
# CSV INITIALIZATION
# =========================

try:
    open(OUTPUT_FILE, "a", encoding="utf-8-sig").close()

except PermissionError:
    print("cars.csv-ը բաց է Excel-ում կամ այլ ծրագրում։")
    print("Փակիր ֆայլը և նորից աշխատեցրու։")
    raise SystemExit


all_rows = []
seen = set()
columns = None

file_lock = threading.Lock()


if os.path.exists(OUTPUT_FILE) and os.path.getsize(OUTPUT_FILE) > 0:

    try:
        old = pd.read_csv(
            OUTPUT_FILE,
            encoding="utf-8-sig"
        )

        all_rows = old.to_dict("records")

        if "url" in old.columns:
            seen = set(
                old["url"].dropna().astype(str)
            )

        columns = list(old.columns)

        print(
            "Շարունակում ենք։ Արդեն կա",
            len(all_rows),
            "մեքենա"
        )

    except Exception as e:
        print("CSV-ի կարդալու սխալ:", e)

        all_rows = []
        seen = set()
        columns = None


# =========================
# SELENIUM DRIVER
# =========================

def make_driver():

    options = Options()

    options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,900")

    options.add_argument(
        "--blink-settings=imagesEnabled=false"
    )

    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--mute-audio")
    options.add_argument("--no-first-run")

    options.add_argument("--renderer-process-limit=1")

    options.add_experimental_option(
        "prefs",
        {
            "profile.managed_default_content_settings.images": 2
        }
    )

    options.page_load_strategy = "eager"

    return webdriver.Chrome(options=options)


all_drivers = []
workers = Queue()


def start_drivers():

    global all_drivers, workers

    all_drivers = []
    workers = Queue()

    for i in range(N_WORKERS):

        driver = make_driver()

        all_drivers.append(driver)
        workers.put(driver)

    print("Selenium drivers started:", N_WORKERS)


def stop_drivers():

    for driver in all_drivers:

        try:
            driver.quit()

        except Exception:
            pass


# =========================
# LISTING URL
# =========================

def get_list_url(page):

    q = {
        "category": "1",
        "page": str(page),
        "sort": "latest",
        "layout": "grid",

        "user": {
            "dealer": "0",
            "official": "0",
            "id": ""
        },

        "year": {
            "gt": "1911",
            "lt": "2027"
        },

        "usdprice": {
            "gt": "0",
            "lt": "100000000"
        },

        "mileage": {
            "gt": "0",
            "lt": "1000000"
        }
    }

    text = json.dumps(
        q,
        separators=(",", ":")
    )

    return (
        "https://auto.am/search/passenger-cars?q="
        + quote(text, safe="{}:,")
    )


# =========================
# GET CAR LINKS
# =========================

def get_item_links(page):

    driver = workers.get()

    try:

        driver.get(get_list_url(page))

        time.sleep(random.uniform(2, 3))

        for i in range(SCROLLS):

            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )

            time.sleep(1)

        links = []
        found = set()

        for a in driver.find_elements(By.TAG_NAME, "a"):

            href = a.get_attribute("href")

            if href and "/offer/" in href:

                href = href.split("?")[0]

                if href not in found:

                    found.add(href)
                    links.append(href)

        return links

    finally:

        workers.put(driver)


# =========================
# NUMBER EXTRACTION
# =========================

def extract_number(text):

    if text is None:
        return None

    digits = re.sub(
        r"[^\d]",
        "",
        str(text)
    )

    if not digits:
        return None

    return float(digits)


def extract_decimal(text):

    if text is None:
        return None

    found = re.search(
        r"\d+(?:[.,]\d+)?",
        str(text)
    )

    if found is None:
        return None

    try:

        return float(
            found.group().replace(",", ".")
        )

    except ValueError:

        return None


# =========================
# PRICE CONVERSION
# =========================

def price_to_usd(text):

    if not text:
        return None

    text = str(text).strip()

    number = extract_number(text)

    if number is None or number <= 0:
        return None

    if "$" in text or "USD" in text.upper():

        return number

    if "€" in text or "EUR" in text.upper():

        return number * EUR_RATE

    if "֏" in text or "AMD" in text.upper():

        return number / USD_RATE

    return None


# =========================
# TARGET LISTING PRICE
# =========================

def extract_listing_price(driver):

    """
    Վերցնում է միայն տվյալ հայտարարության հիմնական գինը։

    Չի որոնում ամբողջ էջի տեքստում,
    որպեսզի չվերցնի առաջարկվող մեքենաների գները։
    """

    try:

        element = driver.find_element(
            By.CSS_SELECTOR,
            ".offer-top-price .price"
        )

        price_text = element.text.strip()

        if not price_text:
            return None

        # Բանակցելի գին
        if "Պայմ" in price_text:
            return None

        # Գինը պետք է պարունակի արժույթի նշան
        if not any(
            symbol in price_text
            for symbol in ["$", "€", "֏", "USD", "EUR", "AMD"]
        ):
            return None

        return price_text

    except Exception:

        return None


# =========================
# TITLE PARSING
# =========================

def split_title(title):

    if not title:
        return None, None, None

    title = re.sub(
        r"[\u200b-\u200f\u2060\ufeff\xa0]",
        " ",
        str(title)
    )

    found = re.search(
        r"(?<!\d)((?:19|20)\d{2})(?!\d)",
        title
    )

    if found is None:
        return None, None, None

    year = int(found.group(1))

    rest = title[found.end():].strip()

    words = rest.split()

    if len(words) < 2:
        return None, None, None

    for name in TWO_WORD_MAKES:

        if rest.lower().startswith(name.lower()):

            return (
                year,
                name,
                rest[len(name):].strip()
            )

    return (
        year,
        words[0],
        " ".join(words[1:])
    )


# =========================
# WAIT FOR DETAILS
# =========================

def wait_for_details(driver):

    try:

        WebDriverWait(driver, 15).until(
            lambda d: "Վազքը" in
            d.find_element(By.TAG_NAME, "body").text
        )

    except Exception:

        print("  Ուշադրություն՝ բնութագրերը չերևացին")


# =========================
# PARSE CAR
# =========================

def parse_item(driver, url):

    driver.get(url)

    wait_for_details(driver)

    row = {
        "url": url
    }

    # ---------------------
    # TITLE
    # ---------------------

    titles = driver.find_elements(
        By.TAG_NAME,
        "h1"
    )

    row["title"] = (
        titles[0].text.strip()
        if titles
        else None
    )

    year, make, model = split_title(
        row["title"]
    )

    row["Year"] = year
    row["Make"] = make
    row["Model"] = model

    # ---------------------
    # PRICE
    # ---------------------

    price = extract_listing_price(driver)

    row["price"] = price

    row["price_usd"] = price_to_usd(
        price
    )

    # ---------------------
    # PAGE TEXT
    # ---------------------

    body_text = driver.execute_script(
        "return document.body.innerText"
    )

    lines = [
        line.strip()
        for line in body_text.split("\n")
        if line.strip()
    ]

    # ---------------------
    # CAR CHARACTERISTICS
    # ---------------------

    for armenian, english in LABELS.items():

        value = None

        for i in range(len(lines)):

            line = lines[i]

            if line == armenian and i + 1 < len(lines):

                value = lines[i + 1]
                break

            if (
                line.startswith(armenian)
                and len(line) > len(armenian)
                and line[len(armenian)] in ["\t", " "]
            ):

                value = line[len(armenian):].strip()
                break

        row[english] = value

    # ---------------------
    # NUMERIC FEATURES
    # ---------------------

    row["Mileage"] = extract_number(
        row["Mileage"]
    )

    row["Engine"] = extract_decimal(
        row["Engine"]
    )

    row["Horsepower"] = extract_number(
        row["Horsepower"]
    )

    row["Cylinders"] = extract_number(
        row["Cylinders"]
    )

    row["Doors"] = extract_number(
        row["Doors"]
    )

    # ---------------------
    # CUSTOMS
    # ---------------------

    row["Customs"] = None

    for line in lines:

        if "Մաքսազերծ" in line:

            row["Customs"] = (
                1
                if "Մաքսազերծված է" in line
                else 0
            )

            break

    return row


# =========================
# SAVE ROW
# =========================

def append_row(row):

    global columns

    with file_lock:

        all_rows.append(row)

        try:

            if columns is None:

                columns = list(row.keys())

            df = pd.DataFrame(
                [row]
            ).reindex(columns=columns)

            file_exists = (
                os.path.exists(OUTPUT_FILE)
                and os.path.getsize(OUTPUT_FILE) > 0
            )

            df.to_csv(
                OUTPUT_FILE,
                mode="a" if file_exists else "w",
                header=not file_exists,
                index=False,
                encoding="utf-8-sig" if not file_exists else "utf-8"
            )

        except OSError:

            print(
                "cars.csv-ը զբաղված է։ "
                "Մեքենան պահվում է backup ֆայլում։"
            )

            backup_exists = (
                os.path.exists(BACKUP_FILE)
                and os.path.getsize(BACKUP_FILE) > 0
            )

            pd.DataFrame([row]).to_csv(
                BACKUP_FILE,
                mode="a" if backup_exists else "w",
                header=not backup_exists,
                index=False,
                encoding="utf-8-sig" if not backup_exists else "utf-8"
            )


# =========================
# SAFE PARSING
# =========================

def safe_parse(url):

    driver = workers.get()

    try:

        row = parse_item(
            driver,
            url
        )

        append_row(row)

        print(
            "Ավտո:",
            len(all_rows),
            "|",
            row.get("title"),
            "| Գին:",
            row.get("price"),
            "| USD:",
            row.get("price_usd"),
            "|",
            row.get("Mileage"),
            "կմ |",
            row.get("Fuel")
        )

        time.sleep(
            random.uniform(0.3, 0.8)
        )

        return row

    except Exception as e:

        print(
            "Սխալ:",
            url,
            e
        )

        return None

    finally:

        workers.put(driver)


# =========================
# MAIN
# =========================

try:

    start_drivers()

    first_page = max(
        START_PAGE,
        len(all_rows) // 50 - 2
    )

    covered_pages = len(all_rows) // 40 + 1

    empty_pages = 0

    for page in range(
        first_page,
        END_PAGE + 1
    ):

        if len(all_rows) >= MAX_CARS:
            break

        # ---------------------
        # RESTART DRIVERS
        # ---------------------

        if (
            page > first_page
            and (page - first_page) % RESTART_EVERY == 0
        ):

            print("Վերագործարկում ենք drivers-ը...")

            stop_drivers()
            start_drivers()

        print("\nԷջ", page)

        links = get_item_links(page)

        print(
            "Գտնվեց հղում:",
            len(links)
        )

        if len(links) == 0:

            print("Էջը դատարկ է։ Կանգ ենք առնում։")
            break

        # ---------------------
        # REMOVE DUPLICATES
        # ---------------------

        links = [
            link
            for link in links
            if link not in seen
        ]

        if len(links) == 0:

            if page <= covered_pages:

                print(
                    "Այս էջը արդեն հավաքված է։ Անցնում ենք։"
                )

                continue

            empty_pages += 1

            if empty_pages >= 3:

                print(
                    "3 էջ անընդմեջ նոր մեքենա չկա։"
                )

                break

        else:

            empty_pages = 0

        links = links[
            :MAX_CARS - len(all_rows)
        ]

        seen.update(links)

        # ---------------------
        # PARALLEL PARSING
        # ---------------------

        with ThreadPoolExecutor(
            max_workers=N_WORKERS
        ) as pool:

            list(
                pool.map(
                    safe_parse,
                    links
                )
            )

        print(
            "Էջ",
            page,
            "ավարտվեց։ Ընդհանուր՝",
            len(all_rows),
            "մեքենա"
        )

finally:

    stop_drivers()


print("\nՊատրաստ է՝", OUTPUT_FILE)


try:

    os.startfile(OUTPUT_FILE)

except Exception:

    pass
