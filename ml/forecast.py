from prophet import Prophet
import pandas as pd


def fill_missing_dates(sku_data):

    df = pd.DataFrame(
        list(sku_data.items()),
        columns=["ds", "y"]
    )

    df["ds"] = pd.to_datetime(df["ds"])

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

    return df


def forecast_sku(df):

    if len(df) < 7:
        return 0

    model = Prophet()

    model.fit(df)

    future = model.make_future_dataframe(periods=60)

    forecast = model.predict(future)

    predicted_qty = round(
        forecast["yhat"].tail(30).sum()
    )

    return max(predicted_qty, 0)


def forecast_all_skus(sales_data):

    results = {}

    for sku, sku_data in sales_data.items():

        try:

            df = fill_missing_dates(sku_data)

            qty = forecast_sku(df)

            results[sku] = {
                "recommended_qty": qty
            }

        except Exception as e:

            results[sku] = {
                "error": str(e)
            }

    return results