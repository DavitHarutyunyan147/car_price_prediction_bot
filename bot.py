import re
import joblib
import telebot
import numpy as np
import pandas as pd

from telebot import types



with open("token.txt", "r", encoding="utf-8") as f:
    BOT_TOKEN = f.read().strip()

bot = telebot.TeleBot(BOT_TOKEN)




saved = joblib.load("car_model.pkl")

model = saved["model"]

columns = saved["columns"]

TEXT_COLUMNS = saved["text_columns"]

NUMBER_COLUMNS = saved["number_columns"]

categories = saved["categories"]

models_by_make = saved["models_by_make"]



DECIMAL_COLUMNS = ["Engine"]

ASK_ORDER = [
    "Make",
    "Model",
    "Year",
    "Mileage",
    "Body",
    "Fuel",
    "Gearbox",
    "Drive",
    "Engine",
    "Horsepower",
    "Condition"
]

QUESTIONS = {
    "Make": "Ո՞ր մակնիշն է։",
    "Model": "Ի՞նչ մոդել է։",
    "Year": "Ո՞ր տարվա է թողարկումը։ Օրինակ՝ 2015",
    "Mileage": "Որքա՞ն է վազքը կմ-ով։ Օրինակ՝ 120000",
    "Body": "Ի՞նչ թափք է։",
    "Fuel": "Ի՞նչ վառելիք է օգտագործում։",
    "Gearbox": "Ի՞նչ փոխանցման տուփ է։",
    "Drive": "Ի՞նչ քարշակ է։",
    "Engine": "Որքա՞ն է շարժիչի ծավալը լիտրով։ Օրինակ՝ 2.0։ Էլեկտրականի համար՝ 0",
    "Horsepower": "Քանի՞ ձիաուժ է։ Եթե չգիտես՝ գրիր 0։",
    "Condition": "Ի՞նչ վիճակում է մեքենան։"
}




answers = {}




def extract_number(text, decimal=False):

    text = str(text).replace(" ", "")

    if decimal:

        found = re.search(
            r"\d+(?:[.,]\d+)?",
            text
        )

        if found is None:
            return None

        return float(
            found.group().replace(",", ".")
        )

    digits = re.sub(r"[^\d]", "", text)

    if digits == "":
        return None

    return float(digits)




def get_options(chat_id, column):

    if column == "Model":

        make = answers[chat_id]["Make"]

        options = models_by_make.get(make, [])

    else:

        options = categories.get(column, [])

    options = [
        value for value in options
        if value != "Unknown"
    ]

    if (
        column not in ["Make", "Model"]
        and "Unknown" in categories.get(column, [])
    ):
        options.append("Չգիտեմ")

    return options




@bot.message_handler(commands=["start", "predict"])
def start(message):

    chat_id = message.chat.id

    answers[chat_id] = {}

    bot.send_message(
        chat_id,
        "Բարև։ Ես մեքենաների գների կանխատեսման բոտն եմ։\n\n"
        "Պատասխանիր հարցերին, և ես կկանխատեսեմ մեքենայի մոտավոր շուկայական գինը։"
    )

    ask(chat_id, 0)




def ask(chat_id, index):

    column = ASK_ORDER[index]

    if column in TEXT_COLUMNS:

        options = get_options(chat_id, column)

        if not options:

            bot.send_message(
                chat_id,
                "Այս մակնիշի համար մոդելներ չգտնվեցին։ "
                "Գրիր /predict՝ նորից սկսելու համար։"
            )

            answers.pop(chat_id, None)
            return

        keyboard = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True,
            row_width=2
        )

        keyboard.add(*options)

        msg = bot.send_message(
            chat_id,
            QUESTIONS[column],
            reply_markup=keyboard
        )

    else:

        msg = bot.send_message(
            chat_id,
            QUESTIONS[column],
            reply_markup=types.ReplyKeyboardRemove()
        )

    bot.register_next_step_handler(
        msg,
        lambda m: save_answer(m, index)
    )




def save_answer(message, index):

    chat_id = message.chat.id

    text = (message.text or "").strip()

    if text.startswith("/"):

        if text in ["/start", "/predict"]:
            start(message)
        else:
            bot.send_message(
                chat_id,
                "Անհայտ հրաման։ Գրիր /predict՝ նորից սկսելու համար։"
            )

        return

    column = ASK_ORDER[index]

    # TEXT ANSWERS
    if column in TEXT_COLUMNS:

        found = None

        for value in get_options(chat_id, column):

            if value.lower() == text.lower():

                found = "Unknown" if value == "Չգիտեմ" else value
                break

        if found is None:

            bot.send_message(
                chat_id,
                "Խնդրում եմ ընտրիր առաջարկված կոճակներից մեկը։"
            )

            ask(chat_id, index)
            return

        answers[chat_id][column] = found

    else:

        number = extract_number(
            text,
            column in DECIMAL_COLUMNS
        )

        if number is None:

            bot.send_message(
                chat_id,
                "Խնդրում եմ գրիր ճիշտ թիվ։"
            )

            ask(chat_id, index)
            return

        if column == "Year" and not 1900 <= number <= 2027:

            bot.send_message(
                chat_id,
                "Խնդրում եմ գրիր ճիշտ տարեթիվ։"
            )

            ask(chat_id, index)
            return

        if column in ["Mileage", "Engine", "Horsepower"] and number < 0:

            bot.send_message(
                chat_id,
                "Բացասական թիվ հնարավոր չէ։ Փորձիր կրկին։"
            )

            ask(chat_id, index)
            return

        if column in ["Engine", "Horsepower"] and number == 0:

            number = np.nan

        answers[chat_id][column] = number

    if index + 1 < len(ASK_ORDER):

        ask(chat_id, index + 1)

    else:

        finish(chat_id)




def finish(chat_id):

    try:

        row = {}

        for column in TEXT_COLUMNS:
            row[column] = answers[chat_id][column]

        for column in NUMBER_COLUMNS:
            row[column] = answers[chat_id][column]

        data = pd.DataFrame(
            [row],
            columns=columns
        )

        prediction_log = model.predict(data)[0]

        price = np.expm1(prediction_log)

        if not np.isfinite(price):
            raise ValueError("Invalid model prediction")

        price = max(0, round(float(price) / 100) * 100)

        bot.send_message(
            chat_id,
            "Կանխատեսվող գինը՝ մոտ $"
            + format(int(price), ","),
            reply_markup=types.ReplyKeyboardRemove()
        )

        bot.send_message(
            chat_id,
            "Նոր կանխատեսման համար գրիր /predict։"
        )

    except Exception as e:

        print("Prediction error:", e)

        bot.send_message(
            chat_id,
            "Կանխատեսման ժամանակ սխալ առաջացավ։ "
            "Փորձիր կրկին՝ /predict հրամանով։",
            reply_markup=types.ReplyKeyboardRemove()
        )

    finally:

        answers.pop(chat_id, None)




print("Car Price Prediction Bot is running...")

bot.infinity_polling(skip_pending=True)
