from prophet import Prophet
from sklearn.metrics import mean_absolute_percentage_error
import pandas as pd
import numpy as np


# =========================================================
# EGYPT HOLIDAYS
# =========================================================

def build_egypt_holidays():

    holidays = pd.DataFrame({
        "holiday": [
            "ramadan",
            "eid_fitr",
            "eid_adha",
            "white_friday",
            "new_year",
        ],

        "ds": pd.to_datetime([
            "2025-03-01",
            "2025-03-30",
            "2025-06-06",
            "2025-11-28",
            "2025-01-01",
        ]),

        "lower_window": [-7, -3, -3, -2, 0],
        "upper_window": [7, 3, 3, 2, 1],
    })

    return holidays


# =========================================================
# DATA CLEANING
# =========================================================

def fill_missing_dates(sku_data):

    df = pd.DataFrame(
        list(sku_data.items()),
        columns=["ds", "y"]
    )

    df["ds"] = pd.to_datetime(df["ds"])

    df = (
        df.groupby("ds")["y"]
        .sum()
        .reset_index()
    )

    df = df.sort_values("ds")

    full_range = pd.date_range(
        start=df["ds"].min(),
        end=df["ds"].max(),
        freq="D"
    )

    df = (
        df.set_index("ds")
        .reindex(full_range, fill_value=0)
        .rename_axis("ds")
        .reset_index()
    )

    df["y"] = df["y"].clip(lower=0)

    return df


# =========================================================
# SKU VALIDATION
# =========================================================

def validate_sku(df):

    total_sales = df["y"].sum()

    active_days = (df["y"] > 0).sum()

    if len(df) < 30:
        return False, "Not enough historical data"

    if total_sales <= 5:
        return False, "Very low sales volume"

    if active_days < 5:
        return False, "Sparse SKU demand"

    return True, None


# =========================================================
# SIMPLE FALLBACK MODEL
# =========================================================

def fallback_forecast(df, forecast_days=90):

    avg_daily_sales = df["y"].mean()

    prediction = round(avg_daily_sales * forecast_days)

    return max(prediction, 0)


# =========================================================
# PROPHET CONFIGURATION
# =========================================================

def build_prophet_model():

    holidays = build_egypt_holidays()

    model = Prophet(
        holidays=holidays,

        interval_width=0.90,

        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,

        seasonality_mode="multiplicative",

        changepoint_prior_scale=0.15,
        seasonality_prior_scale=10,
    )

    return model


# =========================================================
# TRAIN TEST SPLIT
# =========================================================

def split_train_test(df, test_days=90):

    train_df = df.iloc[:-test_days]

    test_df = df.iloc[-test_days:]

    return train_df, test_df


# =========================================================
# MODEL EVALUATION
# =========================================================

def evaluate_model(model, train_df, test_df):

    future = model.make_future_dataframe(
        periods=len(test_df),
        freq="D"
    )

    forecast = model.predict(future)

    predictions = forecast["yhat"].tail(len(test_df)).values

    actuals = test_df["y"].values

    predictions = np.clip(predictions, 0, None)

    mape = mean_absolute_percentage_error(
        actuals + 1,
        predictions + 1
    ) * 100

    accuracy = max(0, round(100 - mape, 2))

    return round(mape, 2), accuracy


# =========================================================
# FORECAST GENERATION
# =========================================================

def generate_forecast(model, df, forecast_days=90):

    model.fit(df)

    future = model.make_future_dataframe(
        periods=forecast_days,
        freq="D"
    )

    forecast = model.predict(future)

    future_forecast = forecast.tail(forecast_days)

    predicted_qty = round(
        future_forecast["yhat"].sum()
    )

    lower_bound = round(
        future_forecast["yhat_lower"].sum()
    )

    upper_bound = round(
        future_forecast["yhat_upper"].sum()
    )

    return {
        "forecast_qty": max(predicted_qty, 0),

        "lower_bound": max(lower_bound, 0),

        "upper_bound": max(upper_bound, 0),
    }


# =========================================================
# MAIN SKU FORECAST
# =========================================================

def forecast_sku(sku_data, forecast_days=90):

    df = fill_missing_dates(sku_data)

    valid, reason = validate_sku(df)

    if not valid:

        fallback_qty = fallback_forecast(
            df,
            forecast_days
        )

        return {
            "model": "fallback",

            "forecast_qty": fallback_qty,

            "reason": reason,
        }

    train_df, test_df = split_train_test(df)

    model = build_prophet_model()

    model.fit(train_df)

    mape, accuracy = evaluate_model(
        model,
        train_df,
        test_df
    )

    final_model = build_prophet_model()

    forecast_results = generate_forecast(
        final_model,
        df,
        forecast_days
    )

    return {
        "model": "prophet",

        "forecast_qty": forecast_results["forecast_qty"],

        "lower_bound": forecast_results["lower_bound"],

        "upper_bound": forecast_results["upper_bound"],

        "mape": mape,

        "accuracy": accuracy,
    }


# =========================================================
# FORECAST ALL SKUS
# =========================================================

def forecast_all_skus(sales_data, forecast_days=90):

    results = {}

    for sku, sku_data in sales_data.items():

        try:

            result = forecast_sku(
                sku_data,
                forecast_days
            )

            results[sku] = result

        except Exception as e:

            results[sku] = {
                "error": str(e)
            }

    return results