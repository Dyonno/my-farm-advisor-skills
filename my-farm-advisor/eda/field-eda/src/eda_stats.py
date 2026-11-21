"""Small statistical helpers for field-level EDA.

The demo dataset has 10 fields per grower, so the tests here are deliberately
nonparametric and report effect sizes alongside p-values. Everything is pure
and deterministic; no randomness is used outside of the plotting jitter, which
is seeded by the caller.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd
from scipy import stats as sps


def bh_adjust(pvalues: Iterable[float]) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values, preserving input order."""
    p = np.asarray(list(pvalues), dtype=float)
    out = np.full(p.shape, np.nan, dtype=float)
    finite = np.isfinite(p)
    if not finite.any():
        return out
    values = p[finite]
    order = np.argsort(values)
    ranked = values[order]
    n = ranked.size
    adjusted = ranked * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    ordered = np.empty(n, dtype=float)
    ordered[order] = np.clip(adjusted, 0.0, 1.0)
    out[finite] = ordered
    return out


def kruskal_summary(frame: pd.DataFrame, value_col: str, group_col: str) -> dict:
    """Kruskal-Wallis test with epsilon-squared effect size."""
    data = frame[[value_col, group_col]].dropna()
    labels = sorted(data[group_col].astype(str).unique())
    groups = [
        data.loc[data[group_col].astype(str) == label, value_col].to_numpy(dtype=float)
        for label in labels
    ]
    groups = [group for group in groups if group.size >= 2]
    if len(groups) < 2:
        return {
            "metric": value_col,
            "test": "kruskal-wallis",
            "statistic": np.nan,
            "p_value": np.nan,
            "effect_size_epsilon_sq": np.nan,
            "n": int(sum(group.size for group in groups)),
            "n_groups": len(groups),
        }
    statistic, p_value = sps.kruskal(*groups)
    n = int(sum(group.size for group in groups))
    k = len(groups)
    epsilon_sq = (statistic - k + 1) / (n - k) if n > k else np.nan
    return {
        "metric": value_col,
        "test": "kruskal-wallis",
        "statistic": float(statistic),
        "p_value": float(p_value),
        "effect_size_epsilon_sq": float(epsilon_sq),
        "n": n,
        "n_groups": k,
    }


def pairwise_mannwhitney(
    frame: pd.DataFrame, value_col: str, group_col: str
) -> pd.DataFrame:
    """Pairwise Mann-Whitney U tests with BH-adjusted p-values."""
    data = frame[[value_col, group_col]].dropna()
    labels = sorted(data[group_col].astype(str).unique())
    rows: list[dict[str, object]] = []
    for index, group_a in enumerate(labels):
        for group_b in labels[index + 1 :]:
            values_a = data.loc[data[group_col].astype(str) == group_a, value_col].to_numpy(
                dtype=float
            )
            values_b = data.loc[data[group_col].astype(str) == group_b, value_col].to_numpy(
                dtype=float
            )
            if values_a.size < 2 or values_b.size < 2:
                continue
            statistic, p_value = sps.mannwhitneyu(
                values_a, values_b, alternative="two-sided"
            )
            rank_biserial = 1.0 - (2.0 * statistic) / (values_a.size * values_b.size)
            rows.append(
                {
                    "metric": value_col,
                    "test": "mann-whitney-u",
                    "group_a": group_a,
                    "group_b": group_b,
                    "statistic": float(statistic),
                    "p_value": float(p_value),
                    "effect_size_rank_biserial": float(rank_biserial),
                    "n_a": int(values_a.size),
                    "n_b": int(values_b.size),
                    "median_a": float(np.median(values_a)),
                    "median_b": float(np.median(values_b)),
                }
            )
    result = pd.DataFrame(rows)
    if not result.empty:
        result["p_bh"] = bh_adjust(result["p_value"])
    return result


def chi_square_summary(table: pd.DataFrame) -> dict:
    """Chi-square test on a contingency table, with Cramer's V."""
    table = table.loc[table.sum(axis=1) > 0, table.sum(axis=0) > 0]
    if table.shape[0] < 2 or table.shape[1] < 2:
        return {
            "test": "chi-square",
            "statistic": np.nan,
            "p_value": np.nan,
            "degrees_of_freedom": 0,
            "effect_size_cramers_v": np.nan,
            "n": int(table.to_numpy().sum()),
            "min_expected": np.nan,
            "warning": "insufficient table dimensions",
        }
    statistic, p_value, dof, expected = sps.chi2_contingency(table, correction=False)
    n = int(table.to_numpy().sum())
    denominator = n * (min(table.shape) - 1)
    cramers_v = float(np.sqrt(statistic / denominator)) if denominator else np.nan
    min_expected = float(expected.min())
    return {
        "test": "chi-square",
        "statistic": float(statistic),
        "p_value": float(p_value),
        "degrees_of_freedom": int(dof),
        "effect_size_cramers_v": cramers_v,
        "n": n,
        "min_expected": min_expected,
        "warning": (
            "some expected counts below 5; treat as exploratory"
            if min_expected < 5
            else ""
        ),
    }


def spearman_long(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Pairwise Spearman correlations with BH-adjusted p-values."""
    rows: list[dict[str, object]] = []
    for index, column_a in enumerate(columns):
        for column_b in columns[index + 1 :]:
            subset = frame[[column_a, column_b]].dropna()
            if len(subset) < 3:
                continue
            rho, p_value = sps.spearmanr(subset[column_a], subset[column_b])
            rows.append(
                {
                    "var_a": column_a,
                    "var_b": column_b,
                    "method": "spearman",
                    "rho": float(rho),
                    "p_value": float(p_value),
                    "n": int(len(subset)),
                }
            )
    result = pd.DataFrame(rows)
    if not result.empty:
        result["p_bh"] = bh_adjust(result["p_value"])
    return result


def coefficient_of_variation(values: pd.Series) -> float:
    """Sample CV, returning NaN for empty or zero-mean samples."""
    clean = pd.Series(values, dtype=float).dropna()
    if clean.empty or clean.mean() == 0:
        return float("nan")
    return float(clean.std(ddof=1) / clean.mean())
