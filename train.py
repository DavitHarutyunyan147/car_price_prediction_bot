import joblib
import numpy as np
import pandas as pd

from xgboost import XGBRegressor

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.impute import SimpleImputer

from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    median_absolute_error
)



df = pd.read_csv("cars.csv")

print("Սկզբնական տվյալներ:", len(df))

df = df.drop_duplicates(subset=["url"]).copy()

TEXT_COLUMNS = [
    "Make", "Model", "Body", "Fuel",
    "Gearbox", "Drive", "Condition"
]

NUMBER_COLUMNS = [
    "Year", "Mileage", "Engine", "Horsepower"
]

FEATURE_COLUMNS = TEXT_COLUMNS + NUMBER_COLUMNS

df["Price"] = pd.to_numeric(
    df["price_usd"], errors="coerce"
)

for column in NUMBER_COLUMNS:
    df[column] = pd.to_numeric(
        df[column], errors="coerce"
    )

for column in TEXT_COLUMNS:
    df[column] = (
        df[column]
        .fillna("Unknown")
        .astype(str)
        .str.strip()
        .replace("", "Unknown")
    )

df = df.dropna(
    subset=["Price", "Year", "Make", "Model"]
).copy()

df = df[
    (df["Price"] > 500) &
    (df["Price"] < 500000)
].copy()

X = df[FEATURE_COLUMNS].copy()
y = df["Price"].copy()

print("Մաքրված տվյալներ:", len(df))



X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)



numeric_transformer = Pipeline([
    ("imputer", SimpleImputer(strategy="median"))
])

categorical_transformer = Pipeline([
    ("imputer", SimpleImputer(strategy="most_frequent")),
    ("encoder", OneHotEncoder(handle_unknown="ignore"))
])

preprocessor = ColumnTransformer([
    ("numeric", numeric_transformer, NUMBER_COLUMNS),
    ("categorical", categorical_transformer, TEXT_COLUMNS)
])



model = XGBRegressor(
    n_estimators=1000,
    max_depth=8,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    objective="reg:squarederror",
    eval_metric="rmse",
    random_state=42,
    n_jobs=-1,
    tree_method="hist"
)



pipeline = Pipeline([
    ("preprocessor", preprocessor),
    ("model", model)
])



print("\nXGBoost ուսուցումը սկսվում է...\n")

y_train_log = np.log1p(y_train)

pipeline.fit(X_train, y_train_log)



predictions_log = pipeline.predict(X_test)

predictions = np.expm1(predictions_log)



results = pd.DataFrame({
    "Actual": y_test.values,
    "Predicted": predictions
})

results["Absolute_Error"] = (
    results["Actual"] - results["Predicted"]
).abs()

bins = [500, 10000, 30000, 60000, 100000, 200000, 500000]

labels = [
    "$500-$10k",
    "$10k-$30k",
    "$30k-$60k",
    "$60k-$100k",
    "$100k-$200k",
    "$200k-$500k"
]

results["Price_Range"] = pd.cut(
    results["Actual"],
    bins=bins,
    labels=labels,
    include_lowest=True
)

print("\n========== RESULTS BY PRICE RANGE ==========")

for price_range, group in results.groupby(
    "Price_Range", observed=False
):
    if len(group) == 0:
        continue

    mae = group["Absolute_Error"].mean()

    print(
        f"{str(price_range):18} | "
        f"Count: {len(group):4} | "
        f"MAE: ${mae:,.2f}"
    )




mae = mean_absolute_error(y_test, predictions)

rmse = np.sqrt(
    mean_squared_error(y_test, predictions)
)

r2 = r2_score(y_test, predictions)

mape = np.mean(
    np.abs((y_test - predictions) / y_test)
) * 100

median_ae = median_absolute_error(
    y_test, predictions
)

print("\n========== XGBOOST RESULTS ==========")
print("MAE:", round(mae, 2), "$")
print("RMSE:", round(rmse, 2), "$")
print("R2:", round(r2, 4))
print("MAPE:", round(mape, 2), "%")
print("Median AE:", round(median_ae, 2), "$")



results = pd.DataFrame({
    "Actual": y_test.values,
    "Predicted": predictions
})

results["Error"] = (
    results["Actual"] - results["Predicted"]
).abs()

print("\nԱմենամեծ սխալներով 10 կանխատեսումները:")

print(
    results
    .sort_values("Error", ascending=False)
    .head(10)
    .round(2)
    .to_string(index=False)
)



categories = {}

for column in TEXT_COLUMNS:
    categories[column] = sorted(
        df[column].dropna().astype(str).unique().tolist()
    )

models_by_make = {}

for make in categories["Make"]:
    models = (
        df.loc[df["Make"] == make, "Model"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    models_by_make[make] = sorted(models)

saved_model = {
    "model": pipeline,
    "columns": FEATURE_COLUMNS,
    "text_columns": TEXT_COLUMNS,
    "number_columns": NUMBER_COLUMNS,
    "categories": categories,
    "models_by_make": models_by_make
}

joblib.dump(saved_model, "car_model.pkl")

print("\nXGBoost մոդելը պահպանվեց։")
