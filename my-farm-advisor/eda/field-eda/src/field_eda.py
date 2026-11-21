"""End-to-end field-level EDA for the demo farms.

The module is a pure orchestration layer: callers supply already-loaded farm
data (boundaries, weather, CDL composition) and receive a manifest describing
the tables and figures that were written. All statistics, metrics, and plotting
live in the sibling modules so each piece can be reused or tested alone.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

import boundary_metrics
import crop_history
import eda_plots
import weather_metrics

IDENTITY = ("grower_slug", "farm_slug", "field_id")
TABLE_FILENAMES = {
    "field_boundary_metrics": "field_boundary_metrics.csv",
    "boundary_comparison": "boundary_comparison.csv",
    "boundary_grower_summary": "boundary_grower_summary.csv",
    "crop_composition": "crop_composition.csv",
    "crop_dominant": "crop_dominant.csv",
    "crop_rotation_summary": "crop_rotation_summary.csv",
    "crop_transitions": "crop_transitions.csv",
    "crop_comparison": "crop_comparison.csv",
    "crop_grower_summary": "crop_grower_summary.csv",
    "weather_seasonal_metrics": "weather_seasonal_metrics.csv",
    "weather_comparison": "weather_comparison.csv",
    "weather_grower_summary": "weather_grower_summary.csv",
    "weather_correlations": "weather_correlations.csv",
    "weather_cells": "weather_cells.csv",
    "field_profile": "field_profile.csv",
}


@dataclass
class FarmData:
    """Raw per-farm inputs required by the EDA."""

    grower_slug: str
    farm_slug: str
    fields: gpd.GeoDataFrame
    weather: pd.DataFrame
    composition: pd.DataFrame
    rotation: pd.DataFrame | None = None
    inputs: dict[str, str] = field(default_factory=dict)


@dataclass
class EdaParams:
    """Analysis knobs and output locations."""

    output_dir: Path
    cdl_start_year: int = 2019
    cdl_end_year: int = 2023
    weather_start_year: int = 2021
    weather_end_year: int = 2025
    gdd_base_temp_c: float = 10.0
    gdd_cap_temp_c: float = 30.0
    growing_season_start_month: int = 4
    growing_season_end_month: int = 9
    dpi: int = 200


def _stamp(frame: pd.DataFrame, grower_slug: str, farm_slug: str) -> pd.DataFrame:
    stamped = frame.copy()
    stamped["grower_slug"] = grower_slug
    stamped["farm_slug"] = farm_slug
    return stamped


def _concat(frames: list[pd.DataFrame], label: str) -> pd.DataFrame:
    non_empty = [frame for frame in frames if frame is not None and not frame.empty]
    if not non_empty:
        raise ValueError(f"no {label} rows available")
    return pd.concat(non_empty, ignore_index=True, sort=False)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_table(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    for column in output.columns:
        if str(output[column].dtype).startswith("datetime"):
            output[column] = output[column].astype(str)
    output.to_csv(path, index=False)
    return {
        "name": path.stem,
        "path": str(path),
        "rows": int(len(output)),
        "columns": list(map(str, output.columns)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _figure_record(path: Path, title: str, story: str) -> dict[str, Any]:
    return {
        "name": path.stem,
        "path": str(path),
        "title": title,
        "story": story,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _validate_farms(farms: list[FarmData]) -> None:
    if not farms:
        raise ValueError("at least one FarmData instance is required")
    for farm in farms:
        if farm.fields is None or farm.fields.empty:
            raise ValueError(f"{farm.grower_slug}/{farm.farm_slug}: field boundaries are empty")
        if "field_id" not in farm.fields.columns:
            raise ValueError(f"{farm.grower_slug}/{farm.farm_slug}: boundaries need field_id")
        if farm.weather is None or farm.weather.empty:
            raise ValueError(f"{farm.grower_slug}/{farm.farm_slug}: weather table is empty")
        if farm.composition is None or farm.composition.empty:
            raise ValueError(f"{farm.grower_slug}/{farm.farm_slug}: CDL composition is empty")


def _headline(
    boundary_tests: pd.DataFrame,
    crop_tests: pd.DataFrame,
    weather_tests: pd.DataFrame,
    metrics: pd.DataFrame,
) -> dict[str, Any]:
    def pick(frame: pd.DataFrame, metric: str, level: str | None = None) -> dict[str, Any]:
        subset = frame.loc[frame["metric"] == metric]
        if level is not None and "level" in subset.columns:
            subset = subset.loc[subset["level"] == level]
        if subset.empty:
            return {}
        row = subset.iloc[0]
        return {
            "p_value": _number(row.get("p_value")),
            "effect_size": _number(
                row.get(
                    "effect_size_epsilon_sq",
                    row.get("effect_size_cramers_v"),
                )
            ),
        }

    return {
        "growers": int(metrics["grower_slug"].nunique()),
        "fields": int(metrics["field_id"].nunique()),
        "total_area_acres": _number(metrics["area_acres"].sum()),
        "median_field_acres": _number(metrics["area_acres"].median()),
        "boundary_area": pick(boundary_tests, "area_acres"),
        "boundary_compactness": pick(boundary_tests, "compactness"),
        "crop_continuous_years": pick(crop_tests, "continuous_years"),
        "weather_gdd_field": pick(weather_tests, "gdd_season", "field"),
        "weather_gdd_cell": pick(weather_tests, "gdd_season", "weather-cell"),
    }


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(numeric) else numeric


def run_eda(
    farms: list[FarmData],
    params: EdaParams,
    counties: gpd.GeoDataFrame | None = None,
) -> dict[str, Any]:
    """Run the full field-level EDA and write static tables and figures."""
    _validate_farms(farms)
    output_dir = Path(params.output_dir)
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    # --- Boundary ---------------------------------------------------------
    fields = _concat(
        [
            _stamp(farm.fields, farm.grower_slug, farm.farm_slug)
            for farm in farms
        ],
        "field boundary",
    )
    fields = gpd.GeoDataFrame(fields, geometry="geometry", crs=farms[0].fields.crs)
    if fields.crs is None:
        fields = fields.set_crs("EPSG:4326")
    if fields["field_id"].duplicated().any():
        duplicates = sorted(
            fields.loc[fields["field_id"].duplicated(), "field_id"].astype(str).unique()
        )
        raise ValueError(
            "field_id must be unique across the selected farms; duplicates: "
            + ", ".join(duplicates[:5])
        )

    boundary = boundary_metrics.compute_metrics(fields)
    boundary_tests = boundary_metrics.compare(boundary)
    boundary_summary = boundary_metrics.grower_summary(boundary)

    # --- Crop history -----------------------------------------------------
    composition = _concat(
        [
            _stamp(farm.composition, farm.grower_slug, farm.farm_slug)
            for farm in farms
        ],
        "CDL composition",
    )
    composition = crop_history.normalize_composition(composition, IDENTITY)
    composition = composition.loc[
        composition["year"].between(params.cdl_start_year, params.cdl_end_year)
    ].copy()
    if composition.empty:
        raise ValueError(
            f"no CDL composition rows between {params.cdl_start_year} and {params.cdl_end_year}"
        )
    dominant = crop_history.dominant_crops(composition, IDENTITY)

    reported_frames = [
        _stamp(farm.rotation, farm.grower_slug, farm.farm_slug)
        for farm in farms
        if farm.rotation is not None and not farm.rotation.empty
    ]
    reported = (
        pd.concat(reported_frames, ignore_index=True, sort=False)
        if reported_frames
        else pd.DataFrame()
    )
    rotation = crop_history.rotation_summary(dominant, reported)
    transitions = crop_history.transition_counts(dominant)
    crop_comparison = crop_history.compare_crop_history(rotation, transitions)

    # --- Weather ----------------------------------------------------------
    weather = _concat(
        [
            _stamp(farm.weather, farm.grower_slug, farm.farm_slug)
            for farm in farms
        ],
        "weather",
    )
    weather = weather.loc[
        pd.to_datetime(weather["date"]).dt.year.between(
            params.weather_start_year, params.weather_end_year
        )
    ].copy()
    prepared = weather_metrics.prepare_daily(
        weather,
        base_temp_c=params.gdd_base_temp_c,
        cap_temp_c=params.gdd_cap_temp_c,
        growing_season_start_month=params.growing_season_start_month,
        growing_season_end_month=params.growing_season_end_month,
    )
    cells = weather_metrics.assign_weather_cells(prepared)
    prepared = prepared.merge(cells, on=list(IDENTITY), how="left")
    seasonal = weather_metrics.seasonal_metrics(prepared, cells)
    weather_comparison = weather_metrics.compare_weather(seasonal)
    weather_correlations = weather_metrics.correlate_weather(seasonal)

    # --- Joined field profile --------------------------------------------
    end_year = int(dominant["year"].max())
    end_crop = dominant.loc[
        dominant["year"].astype(int) == end_year,
        [*IDENTITY, "crop_group", "crop_name", "share_pct"],
    ].rename(
        columns={
            "crop_group": f"crop_group_{end_year}",
            "crop_name": f"crop_name_{end_year}",
            "share_pct": f"crop_share_pct_{end_year}",
        }
    )
    weather_profile = (
        seasonal.groupby(list(IDENTITY), dropna=False)
        .agg(
            mean_gdd_season=("gdd_season", "mean"),
            mean_precip_annual=("precip_annual", "mean"),
            mean_heat_days_30=("heat_days_30", "mean"),
            mean_frost_free_days=("frost_free_days", "mean"),
            weather_cells=("weather_cell_id", "nunique"),
        )
        .reset_index()
    )
    rotation_profile = rotation[
        [*IDENTITY, "rotation_sequence", "crop_diversity", "continuous_years"]
    ]
    profile = boundary_metrics.field_profile_columns(boundary)
    if "crop" in boundary.columns:
        profile["crop"] = boundary["crop"].to_numpy()
    profile = (
        profile.merge(end_crop, on=list(IDENTITY), how="left")
        .merge(rotation_profile, on=list(IDENTITY), how="left")
        .merge(weather_profile, on=list(IDENTITY), how="left")
        .sort_values(["grower_slug", "field_id"])
        .reset_index(drop=True)
    )

    # --- Tables -----------------------------------------------------------
    frames: dict[str, pd.DataFrame] = {
        "field_boundary_metrics": boundary,
        "boundary_comparison": boundary_tests,
        "boundary_grower_summary": boundary_summary,
        "crop_composition": composition,
        "crop_dominant": dominant,
        "crop_rotation_summary": rotation,
        "crop_transitions": transitions,
        "crop_comparison": crop_comparison["comparison"],
        "crop_grower_summary": crop_comparison["grower_summary"],
        "weather_seasonal_metrics": seasonal,
        "weather_comparison": weather_comparison["comparison"],
        "weather_grower_summary": weather_comparison["grower_summary"],
        "weather_correlations": weather_correlations,
        "weather_cells": cells,
        "field_profile": profile,
    }
    table_records = [
        _write_table(frames[name], tables_dir / TABLE_FILENAMES[name])
        for name in TABLE_FILENAMES
    ]

    # --- Figures ----------------------------------------------------------
    medians = boundary.groupby("grower_slug")["area_acres"].median()
    smallest_grower = medians.idxmin()
    smallest_gap = (1.0 - medians.min() / medians.max()) * 100.0
    corn_soy_share = (
        composition.loc[
            composition["crop_group"].isin(["Corn", "Soybeans"]), "pixel_count"
        ].sum()
        / composition["pixel_count"].sum()
        * 100.0
    )
    continuous_rows = rotation.loc[rotation["corn_years"] == rotation["history_years"]]
    continuous_counts = continuous_rows.groupby("grower_slug").size()
    continuous_totals = rotation.groupby("grower_slug").size()
    continuous_text = ", ".join(
        f"{eda_plots.grower_label(grower)} "
        f"{int(continuous_counts.get(grower, 0))}/{int(continuous_totals[grower])}"
        for grower in sorted(continuous_totals.index)
    )
    crop_matches = int(
        (profile["crop_group_2023"].astype(str) == profile["crop"].astype(str)).sum()
    )
    cell_counts = cells.groupby("grower_slug")["weather_cell_id"].nunique()
    fields_per_cell = seasonal.groupby(["grower_slug", "weather_cell_id"])[
        "field_id"
    ].nunique()

    pairwise = boundary_tests.loc[boundary_tests["analysis"] == "mann-whitney-u"]
    area_pairs = pairwise.loc[pairwise["metric"] == "area_acres"]
    area_significant = int((area_pairs["p_bh"] < 0.05).sum())
    shape_effect = float(
        pairwise.loc[
            pairwise["metric"] != "area_acres", "effect_size_rank_biserial"
        ]
        .abs()
        .max()
    )

    crop_kw = crop_comparison["comparison"].loc[
        crop_comparison["comparison"]["analysis"] == "kruskal-wallis"
    ]
    strongest_crop = crop_kw.loc[crop_kw["p_value"].idxmin()]
    chi_row = crop_comparison["comparison"].loc[
        crop_comparison["comparison"]["analysis"] == "chi-square"
    ].iloc[0]
    transition_table = transitions.pivot_table(
        index="grower_slug",
        columns="transition",
        values="count",
        aggfunc="sum",
        fill_value=0,
    )
    transition_observed = transition_table.to_numpy(dtype=float)
    transition_total = transition_observed.sum()
    transition_expected = (
        np.outer(
            transition_observed.sum(axis=1), transition_observed.sum(axis=0)
        )
        / transition_total
    )
    transition_residuals = (transition_observed - transition_expected) / np.sqrt(
        transition_expected
    )
    residual_row, residual_column = np.unravel_index(
        int(np.nanargmax(transition_residuals)), transition_residuals.shape
    )
    excess_grower = eda_plots.grower_label(transition_table.index[residual_row])
    excess_transition = (
        str(transition_table.columns[residual_column])
        .replace(" -> ", " to ")
        .lower()
    )

    weather_epsilon = weather_comparison["comparison"].pivot_table(
        index="metric",
        columns="level",
        values="effect_size_epsilon_sq",
        aggfunc="first",
    )
    gdd_field = float(weather_epsilon.at["gdd_season", "field"])
    gdd_cell = float(weather_epsilon.at["gdd_season", "weather-cell"])
    drops = (weather_epsilon["field"] - weather_epsilon["weather-cell"]).dropna()
    largest_drop_metric = drops.idxmax()
    largest_drop = float(drops.max())

    strongest_positive = weather_correlations.loc[
        weather_correlations["rho"].idxmax()
    ]
    strongest_negative = weather_correlations.loc[
        weather_correlations["rho"].idxmin()
    ]
    significant_correlations = int((weather_correlations["p_bh"] < 0.05).sum())

    figure_specs = [
        (
            "01_field_size_by_grower.png",
            "Field size by grower",
            f"Median field size ranges {medians.min():,.0f}-{medians.max():,.0f} "
            f"acres; {eda_plots.grower_label(smallest_grower)} is smallest, about "
            f"{smallest_gap:.0f}% below the largest grower.",
            lambda path: eda_plots.plot_field_area(
                boundary, boundary_tests, path, params.dpi
            ),
        ),
        (
            "02_shape_vs_area.png",
            "Shape regularity vs field size",
            "Field size weakly predicts shape regularity; IL fields carry the "
            "most boundary vertices, so edge cost varies at similar area.",
            lambda path: eda_plots.plot_compactness_area(boundary, path, params.dpi),
        ),
        (
            "03_field_map.png",
            "Demo farm field layout",
            "Each grower's fields sit in one county; panels are zoomed "
            "independently, so they cannot be compared by eye for absolute size.",
            lambda path: eda_plots.plot_boundary_map(fields, counties, path, params.dpi),
        ),
        (
            "04_crop_composition.png",
            "Crop composition by field and year",
            f"Corn and soybeans supply {corn_soy_share:.1f}% of CDL pixels; "
            "non-crop classes are edge slivers, not whole fields.",
            lambda path: eda_plots.plot_crop_composition(
                composition, path, params.dpi
            ),
        ),
        (
            "05_rotation_heatmap.png",
            "Within-field crop rotation, 2019-2023",
            f"Continuous corn: {continuous_text}. The remaining fields alternate "
            "corn and soybeans.",
            lambda path: eda_plots.plot_rotation_heatmap(
                rotation, dominant, path, params.dpi
            ),
        ),
        (
            f"06_crop_map_{end_year}.png",
            f"Dominant crop in {end_year}",
            f"The {end_year} CDL class matches the grower-reported crop for "
            f"{crop_matches} of {len(profile)} fields.",
            lambda path: eda_plots.plot_crop_map(
                fields, dominant, end_year, counties, path, params.dpi
            ),
        ),
        (
            "07_gdd_curves.png",
            "Cumulative growing degree days",
            "NE accumulates more heat through the season, so the same calendar "
            "date corresponds to a later crop stage there.",
            lambda path: eda_plots.plot_gdd_curves(prepared, path, params.dpi),
        ),
        (
            "08_monthly_precip.png",
            "Monthly precipitation climatology",
            "IA peaks in June-August, IL spreads rain across spring and fall, "
            "and NE is the driest of the three growers overall.",
            lambda path: eda_plots.plot_monthly_precip(prepared, path, params.dpi),
        ),
        (
            "09_weather_map.png",
            "Five-year mean annual precipitation by weather cell",
            f"Weather cells hold {int(fields_per_cell.min())}-"
            f"{int(fields_per_cell.max())} fields; effective spatial replication "
            f"is {int(cell_counts.min())}-{int(cell_counts.max())} cells per grower, "
            "far below the field count.",
            lambda path: eda_plots.plot_weather_map(
                seasonal, fields, counties, path, params.dpi
            ),
        ),
        (
            "10_boundary_comparison_effects.png",
            "Pairwise boundary effects by grower pair",
            f"Area separates {area_significant} of {len(area_pairs)} grower pairs "
            f"after BH correction; no shape metric exceeds |r|={shape_effect:.2f}, "
            "so field geometry does not distinguish the growers.",
            lambda path: eda_plots.plot_boundary_comparison(
                boundary_tests, path, params.dpi
            ),
        ),
        (
            "11_crop_comparison_effects.png",
            "Crop rotation and transition comparisons",
            f"Strongest rotation difference is "
            f"{eda_plots.lower_first(eda_plots.CROP_LABELS[strongest_crop['metric']])} "
            f"(epsilon-squared={float(strongest_crop['effect_size_epsilon_sq']):.2f}, "
            f"p={float(strongest_crop['p_value']):.3f}); "
            f"transition mix differs (chi-square p={float(chi_row['p_value']):.4f}, "
            f"Cramer's V={float(chi_row['effect_size_cramers_v']):.2f}), with "
            f"{excess_grower} over-representing {excess_transition}.",
            lambda path: eda_plots.plot_crop_comparison(
                crop_comparison["comparison"], transitions, path, params.dpi
            ),
        ),
        (
            "12_weather_comparison_effects.png",
            "Weather separation at field and grid-cell level",
            f"GDD separates growers at both levels (field "
            f"epsilon-squared={gdd_field:.2f}, cell={gdd_cell:.2f}); the largest "
            f"field-to-cell drop is {largest_drop:.2f} for "
            f"{eda_plots.lower_first(eda_plots.WEATHER_LABELS[largest_drop_metric])}, so shared "
            "cells are not the driver.",
            lambda path: eda_plots.plot_weather_comparison(
                weather_comparison["comparison"], path, params.dpi
            ),
        ),
        (
            "13_weather_correlation_matrix.png",
            "Weather metric correlations",
            f"{eda_plots.WEATHER_LABELS[strongest_positive['var_a']]} and "
            f"{eda_plots.lower_first(eda_plots.WEATHER_LABELS[strongest_positive['var_b']])} move "
            f"together (rho={float(strongest_positive['rho']):.2f}); "
            f"{eda_plots.lower_first(eda_plots.WEATHER_LABELS[strongest_negative['var_a']])} and "
            f"{eda_plots.lower_first(eda_plots.WEATHER_LABELS[strongest_negative['var_b']])} move "
            f"oppositely (rho={float(strongest_negative['rho']):.2f}); "
            f"{significant_correlations} of {len(weather_correlations)} pairs "
            "survive BH correction.",
            lambda path: eda_plots.plot_weather_correlations(
                weather_correlations, path, params.dpi
            ),
        ),
    ]
    figure_records = []
    for filename, title, story, draw in figure_specs:
        path = figures_dir / filename
        draw(path)
        if not path.exists():
            raise RuntimeError(f"figure was not written: {path}")
        figure_records.append(_figure_record(path, title, story))

    # --- Manifest ---------------------------------------------------------
    manifest: dict[str, Any] = {
        "skill": "field-eda",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "parameters": {
            **asdict(params),
            "output_dir": str(output_dir),
        },
        "inputs": {
            farm.grower_slug: {
                "farm_slug": farm.farm_slug,
                "n_fields": int(farm.fields["field_id"].nunique()),
                "n_weather_rows": int(len(farm.weather)),
                "n_composition_rows": int(len(farm.composition)),
                "paths": farm.inputs,
            }
            for farm in farms
        },
        "tables": table_records,
        "figures": figure_records,
        "headline": _headline(
            boundary_tests,
            crop_comparison["comparison"],
            weather_comparison["comparison"],
            boundary,
        ),
        "notes": [
            "Field-level tests treat each field-year as a sample; weather tests "
            "are repeated at the NASA POWER cell level because field series repeat.",
            "P-values are exploratory; the demo has 10 fields per grower.",
            "Crop shares are recomputed from pixel_count so each field-year sums to 100%.",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest
