from prophet import Prophet
from sklearn.metrics import mean_absolute_percentage_error
from datetime import datetime, timedelta
import pandas as pd
import numpy as np


def _debug_df(label, df, rows=5):
    print(
        f"[forecast-debug][ml] {label}",
        {
            "rows": len(df),
            "columns": list(df.columns),
            "ds_min": df["ds"].min() if "ds" in df else None,
            "ds_max": df["ds"].max() if "ds" in df else None,
            "y_sum": float(df["y"].sum()) if "y" in df else None,
            "y_nonzero_days": int((df["y"] > 0).sum()) if "y" in df else None,
            "nan_counts": df.isna().sum().to_dict(),
        },
    )
    print(df.tail(rows))


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

    print(
        "[forecast-debug][ml] fill_missing_dates input",
        {
            "date_count": len(sku_data),
            "sample": dict(list(sorted(sku_data.items()))[:5]),
            "tail": dict(list(sorted(sku_data.items()))[-5:]),
        },
    )

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

    today = datetime.utcnow().date()
    start_date = today - timedelta(days=365)

    full_range = pd.date_range(
        start=start_date,
        end=today,
        freq="D"
    )

    df = (
        df.set_index("ds")
        .reindex(full_range, fill_value=0)
        .rename_axis("ds")
        .reset_index()
    )

    df["y"] = df["y"].clip(lower=0)

    _debug_df("after fill_missing_dates", df)

    return df


# =========================================================
# SKU VALIDATION
# =========================================================

def validate_sku(df):

    total_sales = df["y"].sum()

    active_days = (df["y"] > 0).sum()

    print(
        "[forecast-debug][ml] validate_sku",
        {
            "rows": len(df),
            "total_sales": float(total_sales),
            "active_days": int(active_days),
            "first_date": df["ds"].min(),
            "last_date": df["ds"].max(),
        },
    )

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

    print(
        "[forecast-debug][ml] fallback_forecast",
        {
            "forecast_days": forecast_days,
            "avg_daily_sales": float(avg_daily_sales),
            "prediction": prediction,
        },
    )

    return max(prediction, 0)


# =========================================================
# PROPHET CONFIGURATION
# =========================================================

def build_prophet_model():

    holidays = build_egypt_holidays()

    model = Prophet(
        holidays=holidays,

        interval_width=0.80,

        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=False,

        seasonality_mode="additive",

        changepoint_prior_scale=0.03,
        seasonality_prior_scale=5,
    )

    return model


# =========================================================
# TRAIN TEST SPLIT
# =========================================================

def split_train_test(df, test_days=90):

    if len(df) < 180:

        print(
            "[forecast-debug][ml] split_train_test skipped",
            {
                "rows": len(df),
                "reason": "Not enough history for train/test evaluation",
                "mape": None,
                "accuracy": None,
            },
        )

        return None, None

    train_df = df.iloc[:-test_days]

    test_df = df.iloc[-test_days:]

    print(
        "[forecast-debug][ml] split_train_test",
        {
            "test_days": test_days,
            "train_rows": len(train_df),
            "test_rows": len(test_df),
            "train_ds_min": train_df["ds"].min() if not train_df.empty else None,
            "train_ds_max": train_df["ds"].max() if not train_df.empty else None,
            "test_ds_min": test_df["ds"].min() if not test_df.empty else None,
            "test_ds_max": test_df["ds"].max() if not test_df.empty else None,
            "train_y_sum": float(train_df["y"].sum()) if not train_df.empty else 0,
            "test_y_sum": float(test_df["y"].sum()) if not test_df.empty else 0,
        },
    )

    return train_df, test_df


# =========================================================
# MODEL EVALUATION
# =========================================================

def evaluate_model(model, train_df, test_df):

    future = model.make_future_dataframe(
        periods=len(test_df),
        freq="D"
    )

    print(
        "[forecast-debug][ml] evaluate future",
        {
            "rows": len(future),
            "tail": future.tail(5).to_dict("records"),
        },
    )

    forecast = model.predict(future)

    print("[forecast-debug][ml] evaluate forecast tail")
    print(forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(20))

    predictions = forecast["yhat"].tail(len(test_df)).values

    actuals = test_df["y"].values

    predictions = np.clip(predictions, 0, None)

    mape = mean_absolute_percentage_error(
        actuals + 1,
        predictions + 1
    ) * 100

    accuracy = max(0, round(100 - mape, 2))

    print(
        "[forecast-debug][ml] evaluate metrics",
        {
            "mape": round(mape, 2),
            "accuracy": accuracy,
            "prediction_min": float(np.min(predictions)) if len(predictions) else None,
            "prediction_max": float(np.max(predictions)) if len(predictions) else None,
            "prediction_sum": float(np.sum(predictions)) if len(predictions) else None,
            "actual_sum": float(np.sum(actuals)) if len(actuals) else None,
        },
    )

    return round(mape, 2), accuracy


# =========================================================
# FORECAST GENERATION
# =========================================================

def generate_forecast(model, df, forecast_days=90):

    _debug_df("generate_forecast training df", df)

    model.fit(df)

    future = model.make_future_dataframe(
        periods=forecast_days,
        freq="D"
    )

    print(
        "[forecast-debug][ml] generate future",
        {
            "forecast_days": forecast_days,
            "rows": len(future),
            "tail": future.tail(10).to_dict("records"),
        },
    )

    forecast = model.predict(future)

    print("[forecast-debug][ml] prophet forecast tail")
    print(forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(20))

    future_forecast = forecast.tail(forecast_days)

    forecast_series = []

    for _, row in future_forecast.iterrows():

        yhat = row["yhat"]
        yhat_lower = row["yhat_lower"]
        yhat_upper = row["yhat_upper"]

        if pd.isna(yhat):
            yhat = 0

        if pd.isna(yhat_lower):
            yhat_lower = 0

        if pd.isna(yhat_upper):
            yhat_upper = 0

        forecast_series.append({
            "ds": row["ds"].strftime("%Y-%m-%d"),
            "yhat": round(float(max(yhat, 0)), 2),
            "yhat_lower": round(float(max(yhat_lower, 0)), 2),
            "yhat_upper": round(float(max(yhat_upper, 0)), 2),
        })

    final_series = future_forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    final_series["ds"] = final_series["ds"].dt.strftime("%Y-%m-%d")

    print(
        "[forecast-debug][ml] final forecast series",
        {
            "rows": len(final_series),
            "nan_counts": future_forecast[["yhat", "yhat_lower", "yhat_upper"]].isna().sum().to_dict(),
            "yhat_sum_raw": float(future_forecast["yhat"].sum()),
            "yhat_min": float(future_forecast["yhat"].min()),
            "yhat_max": float(future_forecast["yhat"].max()),
            "tail": final_series.tail(20).to_dict("records"),
        },
    )

    predicted_qty = round(
        future_forecast["yhat"].clip(lower=0).fillna(0).sum()
    )

    lower_bound = round(
        future_forecast["yhat_lower"].clip(lower=0).fillna(0).sum()
    )

    upper_bound = round(
        future_forecast["yhat_upper"].clip(lower=0).fillna(0).sum()
    )

    result = {
        "forecast_qty": max(predicted_qty, 0),

        "lower_bound": max(lower_bound, 0),

        "upper_bound": max(upper_bound, 0),

        "forecast_series": forecast_series,
    }

    print("[forecast-debug][ml] generate_forecast result", result)

    return result


# =========================================================
# MAIN SKU FORECAST
# =========================================================

def forecast_sku(sku_data, forecast_days=90):

    df = fill_missing_dates(sku_data)

    historical_series = []

    for _, row in df.iterrows():

        historical_series.append({
            "ds": row["ds"].strftime("%Y-%m-%d"),
            "y": round(float(row["y"]), 2),
        })

    valid, reason = validate_sku(df)

    if not valid:

        fallback_qty = fallback_forecast(
            df,
            forecast_days
        )

        result = {
            "model": "fallback",

            "forecast_qty": fallback_qty,

            "reason": reason,

            "historical_series": historical_series,

            "forecast_series": [],
        }

        print("[forecast-debug][ml] forecast_sku fallback result", result)

        return result

    train_df, test_df = split_train_test(df)

    if train_df is None or test_df is None:

        mape = None

        accuracy = None

    else:

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

    result = {
        "model": "prophet",

        "forecast_qty": forecast_results["forecast_qty"],

        "lower_bound": forecast_results["lower_bound"],

        "upper_bound": forecast_results["upper_bound"],

        "mape": mape,

        "accuracy": accuracy,

        "historical_series": historical_series,

        "forecast_series": forecast_results["forecast_series"],
    }

    print("[forecast-debug][ml] forecast_sku prophet result", result)

    return result


# =========================================================
# FORECAST ALL SKUS
# =========================================================

def forecast_all_skus(sales_data, forecast_days=90):

    results = {}

    for sku, sku_data in sales_data.items():

        print(
            "[forecast-debug][ml] forecast_all_skus item",
            {
                "sku": sku,
                "date_count": len(sku_data),
                "total_qty": sum(sku_data.values()),
            },
        )

        try:

            result = forecast_sku(
                sku_data,
                forecast_days
            )

            results[sku] = result

        except Exception as e:

            print(
                "[forecast-debug][ml] forecast_all_skus exception",
                {
                    "sku": sku,
                    "error": str(e),
                    "type": type(e).__name__,
                },
            )

            results[sku] = {
                "model": "error",
                "error": str(e)
            }

    print("[forecast-debug][ml] forecast_all_skus final result", results)

    return results
