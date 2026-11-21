"""CDL crop-history normalization, rotation summaries, and comparisons."""

from __future__ import annotations

import numpy as np
import pandas as pd

import eda_stats

CROP_GROUPS = (
    "Corn",
    "Soybeans",
    "Small grains",
    "Forage",
    "Pasture/Grass",
    "Fallow/Idle",
    "Other/Non-crop",
)

CROP_GROUP_BY_CODE: dict[int, str] = {
    1: "Corn",
    5: "Soybeans",
    21: "Small grains",
    22: "Small grains",
    23: "Small grains",
    24: "Small grains",
    25: "Small grains",
    26: "Small grains",
    27: "Small grains",
    28: "Small grains",
    29: "Small grains",
    30: "Small grains",
    36: "Forage",
    37: "Forage",
    58: "Forage",
    59: "Forage",
    60: "Forage",
    61: "Fallow/Idle",
    62: "Pasture/Grass",
    176: "Pasture/Grass",
}

CROP_PRIORITY = {group: index for index, group in enumerate(CROP_GROUPS)}

SHORT_LABELS = {
    "Corn": "C",
    "Soybeans": "S",
    "Small grains": "W",
    "Forage": "F",
    "Pasture/Grass": "P",
    "Fallow/Idle": "I",
    "Other/Non-crop": "O",
}


def classify_code(crop_code: object) -> str:
    """Map a raw CDL code to a compact EDA group."""
    try:
        code = int(crop_code)
    except (TypeError, ValueError):
        return "Other/Non-crop"
    return CROP_GROUP_BY_CODE.get(code, "Other/Non-crop")


def normalize_composition(composition: pd.DataFrame, identity: tuple[str, ...]) -> pd.DataFrame:
    """Add crop groups and recompute shares from pixel counts.

    The pipeline's ``pct`` column is rounded and can exclude filtered classes.
    EDA uses ``pixel_count`` as the denominator so each field-year sums to 100%.
    """
    required = {"field_id", "year", "crop_code", "crop_name", "pixel_count"}
    missing = required - set(composition.columns)
    if missing:
        raise ValueError(f"CDL composition missing columns: {sorted(missing)}")
    frame = composition.copy()
    frame["year"] = frame["year"].astype(int)
    frame["pixel_count"] = frame["pixel_count"].astype(float)
    frame["crop_group"] = frame["crop_code"].map(classify_code)
    totals = frame.groupby(["field_id", "year"])["pixel_count"].transform("sum")
    frame["share_pct"] = np.where(totals > 0, frame["pixel_count"] / totals * 100.0, 0.0)
    for column in identity:
        if column not in frame.columns:
            raise ValueError(f"CDL composition missing identity column: {column}")
    return frame


def dominant_crops(composition: pd.DataFrame, identity: tuple[str, ...]) -> pd.DataFrame:
    """Pick the dominant crop group for every field-year."""
    frame = composition.copy()
    frame["_priority"] = frame["crop_group"].map(CROP_PRIORITY).fillna(len(CROP_GROUPS))
    frame = frame.sort_values(
        [*identity, "year", "pixel_count", "_priority"],
        ascending=[*[True] * len(identity), True, False, True],
    )
    dominant = frame.drop_duplicates([*identity, "year"], keep="first").copy()
    dominant = dominant.drop(columns=["_priority"])
    return dominant.reset_index(drop=True)


def rotation_summary(dominant: pd.DataFrame, reported: pd.DataFrame) -> pd.DataFrame:
    """Per-field rotation sequence and stability metrics."""
    identity = ["grower_slug", "farm_slug", "field_id"]
    rows: list[dict[str, object]] = []
    for (grower, farm, field_id), group in dominant.groupby(identity, dropna=False):
        ordered = group.sort_values("year")
        sequence = ordered["crop_group"].tolist()
        years = ordered["year"].astype(int).tolist()
        transitions = list(zip(sequence[:-1], sequence[1:]))
        rows.append(
            {
                "grower_slug": grower,
                "farm_slug": farm,
                "field_id": field_id,
                "history_start_year": years[0] if years else np.nan,
                "history_end_year": years[-1] if years else np.nan,
                "history_years": len(years),
                "rotation_sequence": " -> ".join(sequence),
                "rotation_count": len(transitions),
                "corn_years": int(sum(group == "Corn" for group in sequence)),
                "soybean_years": int(sum(group == "Soybeans" for group in sequence)),
                "crop_diversity": len(set(sequence)),
                "continuous_years": int(
                    sum(from_group == to_group for from_group, to_group in transitions)
                ),
            }
        )
    summary = pd.DataFrame(rows)
    reported_columns = [
        column
        for column in (
            "field_id",
            "rotation_sequence",
            "predicted_next_crop",
            "predicted_following_crop",
            "rotation_confidence",
        )
        if column in reported.columns
    ]
    if reported_columns:
        reported_subset = reported[reported_columns].drop_duplicates("field_id")
        summary = summary.merge(reported_subset, on="field_id", how="left", suffixes=("", "_reported"))
        summary["sequence_matches_reported"] = (
            summary["rotation_sequence"] == summary["rotation_sequence_reported"]
        )
    return summary


def transition_counts(dominant: pd.DataFrame) -> pd.DataFrame:
    """Count consecutive-year crop-group transitions per grower."""
    identity = ["grower_slug", "farm_slug", "field_id"]
    ordered = dominant.sort_values([*identity, "year"]).copy()
    ordered["to_group"] = ordered.groupby(identity)["crop_group"].shift(-1)
    ordered = ordered.dropna(subset=["to_group"])
    ordered = ordered.rename(columns={"crop_group": "from_group"})
    ordered["transition"] = ordered["from_group"] + " -> " + ordered["to_group"]
    counts = (
        ordered.groupby(["grower_slug", "from_group", "to_group", "transition"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["grower_slug", "transition"])
    )
    return counts.reset_index(drop=True)


def compare_crop_history(rotation: pd.DataFrame, transitions: pd.DataFrame) -> dict:
    """Tests and summaries for rotation behavior across growers."""
    metrics = ("corn_years", "soybean_years", "crop_diversity", "continuous_years")
    tests = pd.DataFrame(
        [eda_stats.kruskal_summary(rotation, metric, "grower_slug") for metric in metrics]
    )
    tests["analysis"] = "kruskal-wallis"

    summary = (
        rotation.groupby("grower_slug", dropna=False)
        .agg(
            n_fields=("field_id", "nunique"),
            mean_corn_years=("corn_years", "mean"),
            mean_soybean_years=("soybean_years", "mean"),
            mean_crop_diversity=("crop_diversity", "mean"),
            mean_continuous_years=("continuous_years", "mean"),
            continuous_corn_fields=("corn_years", lambda values: int((values == 5).sum())),
        )
        .reset_index()
    )

    transition_table = transitions.pivot_table(
        index="grower_slug",
        columns="transition",
        values="count",
        aggfunc="sum",
        fill_value=0,
    )
    chi = eda_stats.chi_square_summary(transition_table)
    chi_row = pd.DataFrame(
        [
            {
                "analysis": "chi-square",
                "metric": "crop_transitions",
                **chi,
            }
        ]
    )
    comparison = pd.concat([tests, chi_row], ignore_index=True, sort=False)
    return {
        "comparison": comparison,
        "grower_summary": summary,
        "transition_table": transition_table.reset_index(),
    }
