"""Weather metrics, grid-cell detection, and cross-grower comparisons."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

import eda_stats

CORRELATION_METRICS = (
    "gdd_season",
    "precip_annual",
    "precip_growing",
    "heat_days_30",
    "frost_free_days",
    "dry_days",
)

WEATHER_VALUE_COLUMNS = (
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "ALLSKY_SFC_SW_DWN",
    "RH2M",
    "WS10M",
)


def prepare_daily(
    weather: pd.DataFrame,
    *,
    base_temp_c: float,
    cap_temp_c: float,
    growing_season_start_month: int,
    growing_season_end_month: int,
) -> pd.DataFrame:
    """Add year, day-of-year, GDD, and cumulative GDD columns."""
    required = {"grower_slug", "farm_slug", "field_id", "date", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"}
    missing = required - set(weather.columns)
    if missing:
        raise ValueError(f"weather data missing columns: {sorted(missing)}")
    frame = weather.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["year"] = frame["date"].dt.year.astype(int)
    frame["month"] = frame["date"].dt.month.astype(int)
    frame["doy"] = frame["date"].dt.dayofyear.astype(int)
    frame["_in_season"] = frame["month"].between(
        growing_season_start_month, growing_season_end_month
    )
    average_temp = (frame["T2M_MAX"] + frame["T2M_MIN"]) / 2.0
    frame["gdd"] = np.clip(average_temp - base_temp_c, 0.0, cap_temp_c - base_temp_c)
    frame = frame.sort_values(["grower_slug", "farm_slug", "field_id", "date"])
    frame["gdd_cumulative"] = frame.groupby(
        ["grower_slug", "farm_slug", "field_id", "year"], sort=False
    )["gdd"].cumsum()
    return frame.reset_index(drop=True)


def assign_weather_cells(weather: pd.DataFrame) -> pd.DataFrame:
    """Detect fields that share an identical daily NASA POWER series.

    Fields are sampled at centroids, but several centroids fall in the same
    ~0.5 degree POWER grid cell. Identical daily series reveal those shared
    cells, which matters for inference (field count overstates independent n).
    """
    identity = ["grower_slug", "farm_slug", "field_id"]
    signatures: list[dict[str, object]] = []
    for keys, group in weather.groupby(identity, dropna=False):
        ordered = group.sort_values("date")
        values = ordered[list(WEATHER_VALUE_COLUMNS)].to_numpy(dtype=float)
        digest = hashlib.sha1(np.round(values, 4).tobytes()).hexdigest()
        signatures.append(
            {
                "grower_slug": keys[0],
                "farm_slug": keys[1],
                "field_id": keys[2],
                "weather_cell_signature": digest,
            }
        )
    frame = pd.DataFrame(signatures)
    frame["weather_cell_id"] = ""
    farm_numbers = {
        (grower, farm): index + 1
        for index, (grower, farm) in enumerate(
            sorted(
                frame[["grower_slug", "farm_slug"]]
                .drop_duplicates()
                .itertuples(index=False, name=None)
            )
        )
    }
    for (_, _), group in frame.groupby(["grower_slug", "farm_slug"]):
        unique = sorted(group["weather_cell_signature"].unique())
        mapping = {signature: index + 1 for index, signature in enumerate(unique)}
        prefix = str(group["grower_slug"].iloc[0]).split("-")[0]
        farm_number = farm_numbers[
            (str(group["grower_slug"].iloc[0]), str(group["farm_slug"].iloc[0]))
        ]
        ranks = group["weather_cell_signature"].map(mapping)
        frame.loc[group.index, "weather_cell_id"] = [
            f"{prefix}-f{farm_number}-cell-{int(rank):02d}" for rank in ranks
        ]
    return frame.drop(columns=["weather_cell_signature"])


def _frost_metrics(group: pd.DataFrame) -> dict[str, float]:
    cold = group.loc[group["T2M_MIN"] <= 0.0]
    spring = cold.loc[cold["doy"] <= 213, "doy"]
    fall = cold.loc[cold["doy"] >= 214, "doy"]
    last_spring = float(spring.max()) if not spring.empty else np.nan
    first_fall = float(fall.min()) if not fall.empty else np.nan
    frost_free = (
        first_fall - last_spring
        if np.isfinite(last_spring) and np.isfinite(first_fall)
        else np.nan
    )
    return {
        "last_spring_frost_doy": last_spring,
        "first_fall_frost_doy": first_fall,
        "frost_free_days": frost_free,
    }


def seasonal_metrics(
    prepared: pd.DataFrame,
    cells: pd.DataFrame,
) -> pd.DataFrame:
    """One row per field-year with seasonal weather metrics."""
    identity = ["grower_slug", "farm_slug", "field_id", "year"]
    season = prepared.loc[prepared["_in_season"]]
    seasonal = (
        season.groupby(identity, dropna=False)
        .agg(
            gdd_season=("gdd", "sum"),
            precip_growing=("PRECTOTCORR", "sum"),
            heat_days_30=("T2M_MAX", lambda values: int((values >= 30.0).sum())),
            heat_days_35=("T2M_MAX", lambda values: int((values >= 35.0).sum())),
            dry_days=("PRECTOTCORR", lambda values: int((values < 1.0).sum())),
            mean_temp_growing=("T2M", "mean"),
            mean_solar_mj=("ALLSKY_SFC_SW_DWN", "mean"),
            mean_rh_pct=("RH2M", "mean"),
            mean_wind_ms=("WS10M", "mean"),
        )
        .reset_index()
    )
    annual = (
        prepared.groupby(identity, dropna=False)
        .agg(
            gdd_annual=("gdd", "sum"),
            precip_annual=("PRECTOTCORR", "sum"),
            mean_temp_annual=("T2M", "mean"),
        )
        .reset_index()
    )
    frost_rows: list[dict[str, object]] = []
    for keys, group in prepared.groupby(identity, dropna=False):
        row = dict(zip(identity, keys))
        row.update(_frost_metrics(group))
        frost_rows.append(row)
    frost = pd.DataFrame(frost_rows)

    merged = seasonal.merge(annual, on=identity, how="left").merge(
        frost, on=identity, how="left"
    )
    merged = merged.merge(
        cells[["grower_slug", "farm_slug", "field_id", "weather_cell_id"]],
        on=["grower_slug", "farm_slug", "field_id"],
        how="left",
    )
    return merged.sort_values(["grower_slug", "field_id", "year"]).reset_index(drop=True)


def compare_weather(metrics: pd.DataFrame) -> dict:
    """Field-level and grid-cell-level tests across growers."""
    metric_columns = (
        "gdd_season",
        "precip_annual",
        "precip_growing",
        "heat_days_30",
        "frost_free_days",
    )
    field_tests = pd.DataFrame(
        [
            eda_stats.kruskal_summary(metrics, metric, "grower_slug")
            for metric in metric_columns
        ]
    )
    field_tests["level"] = "field"
    field_tests["analysis"] = "kruskal-wallis"

    cell_level = (
        metrics.groupby(
            ["grower_slug", "weather_cell_id", "year"], dropna=False
        )[list(metric_columns)]
        .mean()
        .reset_index()
    )
    cell_tests = pd.DataFrame(
        [
            eda_stats.kruskal_summary(cell_level, metric, "grower_slug")
            for metric in metric_columns
        ]
    )
    cell_tests["level"] = "weather-cell"
    cell_tests["analysis"] = "kruskal-wallis"
    comparison = pd.concat([field_tests, cell_tests], ignore_index=True)

    summary = (
        metrics.groupby("grower_slug", dropna=False)
        .agg(
            n_fields=("field_id", "nunique"),
            n_weather_cells=("weather_cell_id", "nunique"),
            mean_gdd_season=("gdd_season", "mean"),
            mean_precip_annual=("precip_annual", "mean"),
            mean_precip_growing=("precip_growing", "mean"),
            mean_heat_days_30=("heat_days_30", "mean"),
            mean_frost_free_days=("frost_free_days", "mean"),
        )
        .reset_index()
    )
    return {"comparison": comparison, "grower_summary": summary, "cell_level": cell_level}


def correlate_weather(metrics: pd.DataFrame) -> pd.DataFrame:
    """Spearman correlations among seasonal weather metrics."""
    columns = [column for column in CORRELATION_METRICS if column in metrics.columns]
    return eda_stats.spearman_long(metrics, columns)
