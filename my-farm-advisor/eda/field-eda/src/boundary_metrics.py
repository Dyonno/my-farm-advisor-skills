"""Field-boundary metrics and cross-grower comparisons.

All geometry math is performed in EPSG:5070 (Conus Albers, equal-area) so that
area, perimeter, and compactness are meaningful. Centroid coordinates remain in
EPSG:4326 for mapping and joining to weather.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import eda_stats

EQUAL_AREA_CRS = "EPSG:5070"
SQ_METERS_PER_ACRE = 4046.8564224
SQ_METERS_PER_HECTARE = 10_000.0

IDENTITY_COLUMNS = (
    "grower_slug",
    "farm_slug",
    "field_id",
    "state",
    "county",
    "crop",
)
METRICS = ("area_acres", "compactness", "convexity")


def _vertex_count(geometry) -> int:
    if geometry.geom_type == "Polygon":
        return len(geometry.exterior.coords)
    if geometry.geom_type == "MultiPolygon":
        return sum(len(part.exterior.coords) for part in geometry.geoms)
    return 0


def compute_metrics(fields) -> pd.DataFrame:
    """Return one row of boundary metrics per field."""
    import geopandas as gpd

    if not isinstance(fields, gpd.GeoDataFrame):
        raise TypeError("fields must be a GeoDataFrame")
    if fields.crs is None:
        fields = fields.set_crs("EPSG:4326")
    projected = fields.to_crs(EQUAL_AREA_CRS)
    rows: list[dict[str, object]] = []
    for (_, source), geometry, projected_geometry in zip(
        fields.iterrows(), fields.geometry, projected.geometry
    ):
        if geometry is None or geometry.is_empty:
            continue
        area_m2 = float(projected_geometry.area)
        perimeter_m = float(projected_geometry.length)
        hull_area_m2 = float(projected_geometry.convex_hull.area)
        min_x, min_y, max_x, max_y = projected_geometry.bounds
        width_m = max_x - min_x
        height_m = max_y - min_y
        short_side = min(width_m, height_m)
        centroid = geometry.centroid
        compactness = (
            4.0 * np.pi * area_m2 / (perimeter_m**2) if perimeter_m > 0 else np.nan
        )
        row: dict[str, object] = {
            column: source.get(column)
            for column in IDENTITY_COLUMNS
            if column in fields.columns
        }
        row.update(
            {
                "area_m2": area_m2,
                "area_ha": area_m2 / SQ_METERS_PER_HECTARE,
                "area_acres": area_m2 / SQ_METERS_PER_ACRE,
                "perimeter_m": perimeter_m,
                "compactness": float(np.clip(compactness, 0.0, 1.0)),
                "convexity": area_m2 / hull_area_m2 if hull_area_m2 > 0 else np.nan,
                "vertex_count": _vertex_count(projected_geometry),
                "bbox_width_m": width_m,
                "bbox_height_m": height_m,
                "aspect_ratio": (
                    max(width_m, height_m) / short_side if short_side > 0 else np.nan
                ),
                "centroid_lon": float(centroid.x),
                "centroid_lat": float(centroid.y),
                "geometry_type": geometry.geom_type,
                "is_valid": bool(geometry.is_valid),
            }
        )
        rows.append(row)
    if not rows:
        raise ValueError("no valid field geometries found")
    frame = pd.DataFrame(rows)
    if "field_id" not in frame.columns:
        raise ValueError("field boundaries need a field_id property")
    return frame


def compare(metrics: pd.DataFrame) -> pd.DataFrame:
    """Kruskal-Wallis tests plus pairwise Mann-Whitney comparisons."""
    tests = pd.DataFrame(
        [eda_stats.kruskal_summary(metrics, metric, "grower_slug") for metric in METRICS]
    )
    tests["analysis"] = "kruskal-wallis"
    pairwise = [
        eda_stats.pairwise_mannwhitney(metrics, metric, "grower_slug")
        for metric in METRICS
    ]
    pairwise_frame = pd.concat(pairwise, ignore_index=True)
    if not pairwise_frame.empty:
        pairwise_frame["analysis"] = "mann-whitney-u"
    return pd.concat([tests, pairwise_frame], ignore_index=True, sort=False)


def grower_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    """Within-grower spread for area, compactness, and convexity."""
    grouped = metrics.groupby("grower_slug", dropna=False)
    summary = grouped.agg(
        n_fields=("field_id", "nunique"),
        area_acres_median=("area_acres", "median"),
        area_acres_mean=("area_acres", "mean"),
        area_acres_cv=("area_acres", eda_stats.coefficient_of_variation),
        compactness_median=("compactness", "median"),
        compactness_cv=("compactness", eda_stats.coefficient_of_variation),
        convexity_median=("convexity", "median"),
        perimeter_m_median=("perimeter_m", "median"),
    ).reset_index()
    return summary


def field_profile_columns(metrics: pd.DataFrame) -> pd.DataFrame:
    """Subset of metrics used in the joined field profile table."""
    columns = [
        "grower_slug",
        "farm_slug",
        "field_id",
        "state",
        "county",
        "area_acres",
        "perimeter_m",
        "compactness",
        "convexity",
        "vertex_count",
        "centroid_lon",
        "centroid_lat",
    ]
    return metrics[[column for column in columns if column in metrics.columns]].copy()
