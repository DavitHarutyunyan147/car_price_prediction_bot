# Car Price Prediction Bot

An end-to-end machine-learning project that estimates used-car prices from vehicle specifications collected from Auto.am. It combines a Selenium data-collection script, an XGBoost regression pipeline, and a Telegram bot.

## Project components

- **parser.py** — collects Auto.am passenger-car listings and saves vehicle details to `cars.csv`.
- **train.py** — cleans the dataset, preprocesses numeric and categorical features, trains an XGBoost regressor, evaluates it, and exports `car_model.pkl`.
- **bot.py** — asks users for vehicle details in Telegram and returns an estimated price in USD.

## Tech stack

Python, Selenium, pandas, NumPy, scikit-learn, XGBoost, joblib, pyTelegramBotAPI.

## Setup

Use Python 3.10+ and install dependencies:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

python -m pip install -r requirements.txt
```

Chrome and a compatible ChromeDriver are required for Selenium scraping.

## Data collection

Run:

```bash
python parser.py
```

The parser writes collected records to `cars.csv` and resumes from existing records where possible. Review the target website's terms and scrape responsibly; website structure and availability can change.

## Model training

After creating `cars.csv`, run:

```bash
python train.py
```

The training script expects a `price_usd` target and vehicle columns including `Make`, `Model`, `Year`, `Mileage`, `Body`, `Fuel`, `Gearbox`, `Drive`, `Condition`, `Engine`, and `Horsepower`. It saves the trained bundle as `car_model.pkl`.

## Telegram bot

Create a Telegram bot with BotFather, put its token in a local file named `token.txt`, and ensure `car_model.pkl` is present. Then run:

```bash
python bot.py
```

Start the bot in Telegram with `/start` or `/predict`.

## Repository structure

```text
car_price_prediction_bot/
├── parser.py
├── train.py
├── bot.py
├── requirements.txt
├── .gitignore
└── README.md
```

## Important

Do not commit `token.txt`, `.env`, `cars.csv`, `cars_backup.csv`, or generated model files such as `car_model.pkl`. These are local files and are excluded by `.gitignore`.

## Limitations

Predictions are estimates, not professional valuations or guaranteed sale prices. Accuracy depends on dataset coverage, data quality, and changing market conditions.