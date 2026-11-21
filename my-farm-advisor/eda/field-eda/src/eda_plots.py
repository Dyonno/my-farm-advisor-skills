"""Static matplotlib figures for the field-level EDA.

The figures are intentionally plain PNGs (no HTML, no dashboard). Each figure
carries a short takeaway subtitle so it can stand alone in a later report.
"""

from __future__ import annotations

import re
import textwrap

import matplotlib

matplotlib.use("Agg")

import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.cm import ScalarMappable
from matplotlib.colors import ListedColormap, Normalize
from matplotlib.patches import Patch
from scipy import stats as sps

from crop_history import CROP_GROUPS, SHORT_LABELS

PROJECTED_CRS = "EPSG:5070"
PALETTE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9")
GROWER_COLORS = {
    "il-demo-grower": "#0072B2",
    "ia-demo-grower": "#D55E00",
    "ne-demo-grower": "#009E73",
}
CROP_GROUP_COLORS = {
    "Corn": "#E69F00",
    "Soybeans": "#009E73",
    "Small grains": "#F0E442",
    "Forage": "#56B4E9",
    "Pasture/Grass": "#CC79A7",
    "Fallow/Idle": "#999999",
    "Other/Non-crop": "#D9D9D9",
}
YEAR_COLORS = ("#440154", "#3B528B", "#21918C", "#5EC962", "#FDE725")

plt.rcParams.update(
    {
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.grid": True,
        "grid.color": "#e6e6e6",
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
    }
)

_LABEL_HALO = [
    path_effects.withStroke(linewidth=2.0, foreground="white", alpha=0.9)
]


def natural_key(value: object) -> list[object]:
    """Sort ``il-r2`` before ``il-r10``."""
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", str(value))
    ]


def natural_sort_token(value: object) -> str:
    """Hashable natural-sort key suitable for pandas sort columns."""
    return "".join(
        f"{int(part):010d}" if part.isdigit() else part
        for part in re.split(r"(\d+)", str(value))
    )


def grower_label(slug: str) -> str:
    return str(slug).split("-")[0].upper()


def grower_color(slug: str) -> str:
    if slug in GROWER_COLORS:
        return GROWER_COLORS[slug]
    return PALETTE[hash(slug) % len(PALETTE)]


def _save(fig, path, dpi: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _subtitle(ax, text: str) -> None:
    ax.text(
        0.0,
        1.012,
        text,
        transform=ax.transAxes,
        fontsize=7.5,
        color="#555555",
        ha="left",
        va="bottom",
    )


def _title_block(ax, title: str, subtitle: str) -> None:
    ax.set_title(title, loc="left", fontweight="bold", pad=18)
    _subtitle(ax, subtitle)


def _figure_title(fig, title: str, subtitle: str) -> None:
    fig.suptitle(title, x=0.01, y=0.985, ha="left", fontsize=12, fontweight="bold")
    fig.text(0.01, 0.932, subtitle, fontsize=8, color="#555555", ha="left", va="top")


def _wrapped(text: str, width: int = 108) -> str:
    """Wrap a caption so ``bbox_inches='tight'`` does not stretch the canvas."""
    return "\n".join(textwrap.wrap(text, width=width))


def lower_first(text: str) -> str:
    """Lowercase the first letter without mangling acronyms or units like °C."""
    return text[:1].lower() + text[1:]


def _plot_counties(ax, counties) -> None:
    if counties is None or counties.empty:
        return
    counties.plot(
        ax=ax,
        facecolor="#f7f4ed",
        edgecolor="#d7d0c2",
        linewidth=0.55,
        zorder=0,
    )


def _projected_counties(counties):
    if counties is None or counties.empty:
        return None
    return counties.to_crs(PROJECTED_CRS)


def _nearby_counties(projected_counties, subset, buffer_m: float = 3000.0):
    if projected_counties is None or subset.empty:
        return None
    footprint = subset.geometry.buffer(buffer_m)
    footprint = (
        footprint.union_all() if hasattr(footprint, "union_all") else footprint.unary_union
    )
    return projected_counties.loc[projected_counties.geometry.intersects(footprint)]


def _focus(ax, subset, padding: float = 0.08) -> None:
    min_x, min_y, max_x, max_y = subset.total_bounds
    pad_x = (max_x - min_x) * padding or 1000.0
    pad_y = (max_y - min_y) * padding or 1000.0
    ax.set_xlim(min_x - pad_x, max_x + pad_x)
    ax.set_ylim(min_y - pad_y, max_y + pad_y)
    ax.set_aspect("equal")
    ax.axis("off")


def _panel_title(ax, grower: str, n_fields: int) -> None:
    ax.set_title(
        f"{grower_label(grower)} · {n_fields} fields",
        loc="left",
        fontsize=10,
        fontweight="bold",
    )


def _grower_panels(fields, figsize_per_panel=(4.3, 4.5)):
    growers = sorted(fields["grower_slug"].unique())
    fig, axes = plt.subplots(
        1,
        len(growers),
        figsize=(figsize_per_panel[0] * len(growers), figsize_per_panel[1]),
        squeeze=False,
    )
    return growers, fig, axes[0]


def _short_field_id(field_id: object) -> str:
    text = str(field_id)
    if "-r" in text:
        return "r" + text.rsplit("-r", 1)[1]
    return text


def _annotate_fields(ax, subset, fontsize: float = 6.0) -> None:
    """Label fields at their representative point, nudging overlaps apart."""
    points = subset.geometry.representative_point()
    renderer = ax.figure.canvas.get_renderer()
    placed = []
    offsets = (
        (0, 0),
        (0, 10),
        (0, -10),
        (12, 6),
        (-12, 6),
        (12, -6),
        (-12, -6),
        (0, 20),
        (0, -20),
        (18, 0),
        (-18, 0),
    )
    for (_, row), point in zip(subset.iterrows(), points):
        label = _short_field_id(row["field_id"])
        chosen = None
        for offset_x, offset_y in offsets:
            text = ax.annotate(
                label,
                (point.x, point.y),
                textcoords="offset points",
                xytext=(offset_x, offset_y),
                fontsize=fontsize,
                ha="center",
                va="center",
                color="#1a1a1a",
                zorder=5,
                path_effects=_LABEL_HALO,
            )
            box = text.get_window_extent(renderer=renderer).expanded(1.12, 1.12)
            if all(not box.overlaps(other) for other in placed):
                chosen = text
                break
            text.remove()
        if chosen is None:
            chosen = ax.annotate(
                label,
                (point.x, point.y),
                fontsize=fontsize,
                ha="center",
                va="center",
                color="#1a1a1a",
                zorder=5,
                path_effects=_LABEL_HALO,
            )
        placed.append(chosen.get_window_extent(renderer=renderer).expanded(1.12, 1.12))


def plot_field_area(metrics: pd.DataFrame, comparison: pd.DataFrame, path, dpi: int) -> None:
    """Box + strip plot of field area by grower."""
    growers = sorted(metrics["grower_slug"].unique())
    data = [
        metrics.loc[metrics["grower_slug"] == grower, "area_acres"].dropna().to_numpy()
        for grower in growers
    ]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    boxes = ax.boxplot(
        data,
        patch_artist=True,
        widths=0.55,
        showfliers=False,
        medianprops={"color": "#222222", "linewidth": 1.4},
        whiskerprops={"color": "#555555"},
        capprops={"color": "#555555"},
        boxprops={"linewidth": 0.8},
    )
    for patch, grower in zip(boxes["boxes"], growers):
        color = grower_color(grower)
        patch.set_facecolor(color)
        patch.set_alpha(0.22)
        patch.set_edgecolor(color)
    generator = np.random.default_rng(20261115)
    for index, (grower, values) in enumerate(zip(growers, data), start=1):
        color = grower_color(grower)
        jitter = generator.uniform(-0.12, 0.12, values.size)
        ax.scatter(
            index + jitter,
            values,
            s=26,
            color=color,
            edgecolor="white",
            linewidth=0.5,
            zorder=3,
            alpha=0.9,
        )
        for value in (values.min(), values.max()):
            ax.annotate(
                f"{value:,.0f}",
                (index, value),
                textcoords="offset points",
                xytext=(10, 0),
                fontsize=6.5,
                color=color,
                va="center",
            )
    ax.set_xticks(range(1, len(growers) + 1))
    ax.set_xticklabels(
        [f"{grower_label(grower)}\n(n={len(values)})" for grower, values in zip(growers, data)]
    )
    ax.set_ylabel("Field area (acres)")

    medians = metrics.groupby("grower_slug")["area_acres"].median()
    smallest = medians.idxmin()
    test = comparison.loc[
        (comparison["analysis"] == "kruskal-wallis")
        & (comparison["metric"] == "area_acres")
    ]
    p_value = float(test.iloc[0]["p_value"]) if not test.empty else float("nan")
    epsilon = (
        float(test.iloc[0]["effect_size_epsilon_sq"]) if not test.empty else float("nan")
    )
    _title_block(
        ax,
        "Field size by grower",
        f"Median size {medians.min():,.0f}-{medians.max():,.0f} acres; "
        f"{grower_label(smallest)} is smallest. "
        f"Kruskal-Wallis p={p_value:.3g}, epsilon-squared={epsilon:.2f}.",
    )
    _save(fig, path, dpi)


def plot_compactness_area(metrics: pd.DataFrame, path, dpi: int) -> None:
    """Scatter of shape regularity against field size."""
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    for grower in sorted(metrics["grower_slug"].unique()):
        subset = metrics.loc[metrics["grower_slug"] == grower]
        ax.scatter(
            subset["area_acres"],
            subset["compactness"],
            s=46,
            color=grower_color(grower),
            edgecolor="white",
            linewidth=0.6,
            label=f"{grower_label(grower)} (n={len(subset)})",
            zorder=3,
        )
    median = float(metrics["compactness"].median())
    ax.axhline(
        median,
        color="#777777",
        linestyle=":",
        linewidth=1.0,
        label=f"Median compactness = {median:.2f}",
    )
    irregular = metrics.nsmallest(3, "compactness")
    largest = metrics.nlargest(3, "area_acres")
    labelled = pd.concat([irregular, largest]).drop_duplicates("field_id")
    for _, row in labelled.iterrows():
        ax.annotate(
            str(row["field_id"]),
            (row["area_acres"], row["compactness"]),
            textcoords="offset points",
            xytext=(5, 5),
            fontsize=6.5,
            color="#333333",
            path_effects=_LABEL_HALO,
        )
    ax.set_xlabel("Field area (acres)")
    ax.set_ylabel("Polsby-Popper compactness (1 = circle)")
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(0.0, -0.16),
        ncol=2,
        frameon=False,
    )

    rho, p_value = sps.spearmanr(metrics["area_acres"], metrics["compactness"])
    most_vertices = metrics.groupby("grower_slug")["vertex_count"].median().idxmax()
    _title_block(
        ax,
        "Shape regularity vs field size",
        f"Field size weakly predicts regularity (Spearman rho={rho:.2f}, "
        f"p={p_value:.2f}); {grower_label(most_vertices)} fields carry the most "
        "boundary vertices.",
    )
    _save(fig, path, dpi)


def plot_boundary_map(fields, counties, path, dpi: int) -> None:
    """Static map of all demo fields, one panel per grower."""
    growers, fig, axes = _grower_panels(fields)
    projected = fields.to_crs(PROJECTED_CRS)
    projected_counties = _projected_counties(counties)
    handles = []
    for ax, grower in zip(axes, growers):
        subset = projected.loc[projected["grower_slug"] == grower]
        color = grower_color(grower)
        _plot_counties(ax, _nearby_counties(projected_counties, subset))
        subset.plot(
            ax=ax,
            facecolor=color,
            edgecolor=color,
            alpha=0.45,
            linewidth=1.0,
            zorder=2,
        )
        _focus(ax, subset)
        _annotate_fields(ax, subset)
        _panel_title(ax, grower, subset["field_id"].nunique())
        handles.append(
            Patch(facecolor=color, edgecolor=color, alpha=0.6, label=grower_label(grower))
        )
    _figure_title(
        fig,
        "Demo farm field layout",
        "Thirty real USDA CSB fields, one county per grower. Each panel is zoomed "
        "to its own grower, so panel scale differs.",
    )
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=len(handles),
        frameon=False,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.subplots_adjust(left=0.02, right=0.98, top=0.82, bottom=0.10, wspace=0.08)
    _save(fig, path, dpi)


def plot_crop_composition(composition: pd.DataFrame, path, dpi: int) -> None:
    """Small-multiple 100% stacked bars of crop composition."""
    growers = sorted(composition["grower_slug"].unique())
    years = sorted(composition["year"].astype(int).unique())
    fig, axes = plt.subplots(
        len(growers),
        len(years),
        figsize=(2.55 * len(years), 2.35 * len(growers)),
        sharey="row",
        squeeze=False,
    )
    for row_index, grower in enumerate(growers):
        fields = sorted(
            composition.loc[composition["grower_slug"] == grower, "field_id"].unique(),
            key=natural_key,
        )
        for column_index, year in enumerate(years):
            ax = axes[row_index][column_index]
            subset = composition.loc[
                (composition["grower_slug"] == grower)
                & (composition["year"].astype(int) == year)
            ]
            pivot = (
                subset.pivot_table(
                    index="field_id",
                    columns="crop_group",
                    values="share_pct",
                    aggfunc="sum",
                    fill_value=0.0,
                )
                .reindex(fields)
                .fillna(0.0)
            )
            left = np.zeros(len(fields))
            for group in CROP_GROUPS:
                if group not in pivot.columns:
                    continue
                values = pivot[group].to_numpy(dtype=float)
                ax.barh(
                    np.arange(len(fields)),
                    values,
                    left=left,
                    color=CROP_GROUP_COLORS[group],
                    height=0.82,
                    linewidth=0,
                )
                left += values
            ax.set_xlim(0, 100)
            ax.set_ylim(-0.5, len(fields) - 0.5)
            ax.set_yticks(np.arange(len(fields)))
            if column_index == 0:
                ax.set_yticklabels(fields, fontsize=5.8)
            ax.tick_params(axis="y", labelleft=column_index == 0, length=2)
            ax.set_xticks([0, 50, 100])
            ax.tick_params(axis="x", labelsize=5.8)
            if row_index == 0:
                ax.set_title(str(year), fontsize=9)
            if column_index == 0:
                ax.set_ylabel(grower_label(grower), fontsize=8)
            for spine in ax.spines.values():
                spine.set_linewidth(0.4)
    handles = [
        Patch(facecolor=CROP_GROUP_COLORS[group], label=group) for group in CROP_GROUPS
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=min(len(CROP_GROUPS), 7),
        frameon=False,
        bbox_to_anchor=(0.5, 0.005),
    )
    _figure_title(
        fig,
        "Crop composition by field and year (share of CDL pixels)",
        "Corn and soybeans account for 98.9% of pixels; non-crop classes are "
        "mostly field-edge slivers, not whole fields.",
    )
    fig.subplots_adjust(left=0.09, right=0.99, top=0.83, bottom=0.11, wspace=0.10, hspace=0.20)
    _save(fig, path, dpi)


def plot_rotation_heatmap(rotation: pd.DataFrame, dominant: pd.DataFrame, path, dpi: int) -> None:
    """Heatmap of dominant crop group per field-year."""
    years = sorted(dominant["year"].astype(int).unique())
    ordered = rotation.copy()
    ordered["_sort_token"] = ordered["field_id"].map(natural_sort_token)
    ordered = ordered.sort_values(["grower_slug", "_sort_token"])
    fields = ordered["field_id"].tolist()
    grower_by_field = dict(zip(ordered["field_id"], ordered["grower_slug"]))
    pivot = (
        dominant.pivot_table(
            index="field_id", columns="year", values="crop_group", aggfunc="first"
        )
        .reindex(fields)
    )
    index_by_group = {group: index for index, group in enumerate(CROP_GROUPS)}
    matrix = np.full((len(fields), len(years)), index_by_group["Other/Non-crop"], dtype=float)
    for column_index, year in enumerate(years):
        for row_index, field_id in enumerate(fields):
            group = pivot.at[field_id, year] if year in pivot.columns else None
            matrix[row_index, column_index] = index_by_group.get(group, index_by_group["Other/Non-crop"])

    cmap = ListedColormap([CROP_GROUP_COLORS[group] for group in CROP_GROUPS])
    fig, ax = plt.subplots(figsize=(6.4, 8.2))
    ax.imshow(
        matrix,
        aspect="auto",
        cmap=cmap,
        vmin=-0.5,
        vmax=len(CROP_GROUPS) - 0.5,
        interpolation="nearest",
    )
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([str(year) for year in years])
    ax.set_yticks(range(len(fields)))
    ax.set_yticklabels(fields, fontsize=6.2)
    ax.grid(False)
    for row_index in range(len(fields)):
        for column_index in range(len(years)):
            group = CROP_GROUPS[int(matrix[row_index, column_index])]
            ax.text(
                column_index,
                row_index,
                SHORT_LABELS[group],
                ha="center",
                va="center",
                fontsize=6.5,
                color="#1a1a1a",
            )
    # Separate grower blocks.
    current = None
    for row_index, field_id in enumerate(fields):
        grower = grower_by_field[field_id]
        if current is not None and grower != current:
            ax.axhline(row_index - 0.5, color="#222222", linewidth=1.1)
        current = grower
        if row_index == 0 or grower_by_field[fields[row_index - 1]] != grower:
            block = [f for f in fields if grower_by_field[f] == grower]
            center = row_index + (len(block) - 1) / 2
            ax.text(
                1.02,
                center,
                grower_label(grower),
                transform=ax.get_yaxis_transform(),
                fontsize=8,
                fontweight="bold",
                va="center",
                color=grower_color(grower),
            )
    handles = [Patch(facecolor=CROP_GROUP_COLORS[group], label=group) for group in CROP_GROUPS]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.05),
        ncol=4,
        frameon=False,
    )

    continuous = rotation.loc[rotation["corn_years"] == rotation["history_years"]]
    counts = continuous.groupby("grower_slug").size()
    totals = rotation.groupby("grower_slug").size()
    count_text = ", ".join(
        f"{grower_label(grower)} {int(counts.get(grower, 0))}/{int(totals[grower])}"
        for grower in sorted(totals.index)
    )
    _title_block(
        ax,
        "Within-field crop rotation, 2019-2023",
        f"Continuous corn: {count_text}. The other fields alternate corn and soybeans.",
    )
    _save(fig, path, dpi)


def plot_crop_map(fields, dominant: pd.DataFrame, year: int, counties, path, dpi: int) -> None:
    """Map of the dominant crop group in one year, one panel per grower."""
    subset_columns = dominant.loc[
        dominant["year"].astype(int) == year, ["field_id", "crop_group"]
    ]
    merged = fields.merge(subset_columns, on="field_id", how="left")
    growers, fig, axes = _grower_panels(merged)
    projected = merged.to_crs(PROJECTED_CRS)
    projected_counties = _projected_counties(counties)
    handles = []
    for ax, grower in zip(axes, growers):
        subset = projected.loc[projected["grower_slug"] == grower]
        _plot_counties(ax, _nearby_counties(projected_counties, subset))
        for group in CROP_GROUPS:
            block = subset.loc[subset["crop_group"] == group]
            if block.empty:
                continue
            color = CROP_GROUP_COLORS[group]
            block.plot(
                ax=ax,
                facecolor=color,
                edgecolor="#333333",
                linewidth=0.5,
                alpha=0.85,
                zorder=2,
            )
        _focus(ax, subset)
        _annotate_fields(ax, subset)
        _panel_title(ax, grower, subset["field_id"].nunique())
    for group in CROP_GROUPS:
        if merged["crop_group"].eq(group).any():
            handles.append(
                Patch(
                    facecolor=CROP_GROUP_COLORS[group],
                    edgecolor="#333333",
                    label=group,
                )
            )
    matches = (
        int((merged["crop_group"].astype(str) == merged["crop"].astype(str)).sum())
        if "crop" in merged.columns
        else len(merged)
    )
    _figure_title(
        fig,
        f"Dominant crop in {year}",
        f"The {year} CDL class matches the grower-reported crop for {matches} of "
        f"{len(merged)} fields.",
    )
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=len(handles),
        frameon=False,
        bbox_to_anchor=(0.5, 0.0),
        title=f"Dominant crop {year}",
    )
    fig.subplots_adjust(left=0.02, right=0.98, top=0.82, bottom=0.12, wspace=0.08)
    _save(fig, path, dpi)


def plot_gdd_curves(prepared: pd.DataFrame, path, dpi: int) -> None:
    """Cumulative GDD curves by grower, year, and field."""
    season = prepared.loc[prepared["_in_season"]]
    growers = sorted(season["grower_slug"].unique())
    years = sorted(season["year"].astype(int).unique())
    colors = YEAR_COLORS[: len(years)]
    if len(colors) < len(years):
        colors = plt.cm.viridis(np.linspace(0.15, 0.9, len(years)))
    fig, axes = plt.subplots(1, len(growers), figsize=(11.0, 4.4), sharey=True)
    if len(growers) == 1:
        axes = [axes]
    month_ticks = [91, 121, 152, 182, 213, 244, 274]
    month_labels = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"]
    for ax, grower in zip(axes, growers):
        subset = season.loc[season["grower_slug"] == grower]
        for year, color in zip(years, colors):
            year_subset = subset.loc[subset["year"].astype(int) == year]
            if year_subset.empty:
                continue
            for _, field_group in year_subset.groupby("field_id"):
                ax.plot(
                    field_group["doy"],
                    field_group["gdd_cumulative"],
                    color=color,
                    alpha=0.16,
                    linewidth=0.8,
                )
            mean_curve = year_subset.groupby("doy")["gdd_cumulative"].mean()
            ax.plot(
                mean_curve.index,
                mean_curve.values,
                color=color,
                linewidth=2.0,
                label=str(year),
            )
        ax.set_xticks(month_ticks)
        ax.set_xticklabels(month_labels)
        ax.set_xlabel("Month")
        ax.set_title(grower_label(grower), loc="left")
    axes[0].set_ylabel("Cumulative GDD (°C-days)")
    axes[0].legend(title="Year", loc="upper left", frameon=True, fontsize=7)
    _figure_title(
        fig,
        "Cumulative growing degree days (base 10 °C, cap 30 °C)",
        "Thin lines are individual fields; thick lines are the grower mean. "
        "NE accumulates more heat by the same calendar date.",
    )
    fig.subplots_adjust(left=0.06, right=0.99, top=0.80, bottom=0.13, wspace=0.08)
    _save(fig, path, dpi)


def plot_monthly_precip(prepared: pd.DataFrame, path, dpi: int) -> None:
    """Monthly precipitation climatology with the five-year range."""
    growers = sorted(prepared["grower_slug"].unique())
    fig, axes = plt.subplots(1, len(growers), figsize=(11.0, 4.0), sharey=True)
    if len(growers) == 1:
        axes = [axes]
    for ax, grower in zip(axes, growers):
        subset = prepared.loc[prepared["grower_slug"] == grower]
        # Sum each cell's daily values, then average across cells so fields in
        # the same NASA POWER cell do not multiply the total.
        group_column = (
            "weather_cell_id" if "weather_cell_id" in subset.columns else "field_id"
        )
        daily = (
            subset.groupby(["year", "month", group_column])["PRECTOTCORR"]
            .sum()
            .reset_index()
        )
        monthly = daily.groupby(["year", "month"])["PRECTOTCORR"].mean().reset_index()
        stats = monthly.groupby("month")["PRECTOTCORR"].agg(["mean", "min", "max"])
        stats = stats.reindex(range(1, 13)).fillna(0.0)
        color = grower_color(grower)
        ax.bar(
            stats.index,
            stats["mean"],
            color=color,
            alpha=0.75,
            edgecolor="white",
            linewidth=0.5,
        )
        lower = stats["mean"] - stats["min"]
        upper = stats["max"] - stats["mean"]
        ax.errorbar(
            stats.index,
            stats["mean"],
            yerr=[lower, upper],
            fmt="none",
            ecolor="#333333",
            elinewidth=0.8,
            capsize=2,
        )
        ax.axvspan(3.5, 9.5, color="#f2e6c9", alpha=0.35, zorder=0)
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(list("JFMAMJJASOND"))
        ax.set_xlabel("Month")
        ax.set_title(grower_label(grower), loc="left")
    axes[0].set_ylabel("Monthly precipitation (mm)")
    _figure_title(
        fig,
        "Monthly precipitation climatology, 2021-2025",
        "Bars: five-year mean per grid cell; whiskers: observed range; band: "
        "Apr-Sep. IA peaks in Jun-Aug; IL is wetter in spring and fall; NE is driest.",
    )
    fig.subplots_adjust(left=0.06, right=0.99, top=0.80, bottom=0.13, wspace=0.08)
    _save(fig, path, dpi)


def plot_weather_map(metrics: pd.DataFrame, fields, counties, path, dpi: int) -> None:
    """Field-centroid map colored by mean annual precipitation, one panel per grower.

    Bubbles are NASA POWER grid cells rather than fields: fields inside a cell
    share one weather series, so one bubble per cell keeps the effective
    replication visible.
    """
    cell_metrics = (
        metrics.groupby(["grower_slug", "weather_cell_id"], dropna=False)
        .agg(
            mean_precip_annual=("precip_annual", "mean"),
            n_fields=("field_id", "nunique"),
        )
        .reset_index()
    )
    field_cells = metrics[["grower_slug", "field_id", "weather_cell_id"]].drop_duplicates()
    projected = fields.merge(field_cells, on=["grower_slug", "field_id"], how="inner").to_crs(
        PROJECTED_CRS
    )
    points = projected.geometry.representative_point()
    projected["_x"] = points.x
    projected["_y"] = points.y
    centroids = (
        projected.groupby(["grower_slug", "weather_cell_id"], dropna=False)[["_x", "_y"]]
        .mean()
        .reset_index()
    )
    cells = cell_metrics.merge(
        centroids, on=["grower_slug", "weather_cell_id"], how="left"
    )

    growers, fig, axes = _grower_panels(fields)
    projected_fields = fields.to_crs(PROJECTED_CRS)
    projected_counties = _projected_counties(counties)
    values = cells["mean_precip_annual"].to_numpy(dtype=float)
    norm = Normalize(vmin=float(np.nanmin(values)), vmax=float(np.nanmax(values)))
    cmap = plt.cm.YlGnBu
    for ax, grower in zip(axes, growers):
        subset = projected_fields.loc[projected_fields["grower_slug"] == grower]
        _plot_counties(ax, _nearby_counties(projected_counties, subset))
        subset.plot(
            ax=ax,
            facecolor="none",
            edgecolor="#555555",
            linewidth=0.6,
            zorder=2,
        )
        _focus(ax, subset, padding=0.14)
        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()
        x_span = x_max - x_min
        y_span = y_max - y_min
        cell_subset = cells.loc[cells["grower_slug"] == grower]
        ax.scatter(
            cell_subset["_x"],
            cell_subset["_y"],
            c=cell_subset["mean_precip_annual"],
            cmap=cmap,
            norm=norm,
            s=40 + 22 * cell_subset["n_fields"],
            edgecolor="#222222",
            linewidth=0.6,
            zorder=3,
        )
        for _, row in cell_subset.iterrows():
            count = int(row["n_fields"])
            offset_x = 0.0
            horizontal_alignment = "center"
            if row["_x"] > x_max - 0.15 * x_span:
                offset_x = -4.0
                horizontal_alignment = "right"
            elif row["_x"] < x_min + 0.15 * x_span:
                offset_x = 4.0
                horizontal_alignment = "left"
            offset_y = -13.0 if row["_y"] > y_max - 0.10 * y_span else 9.0
            ax.annotate(
                f"{count} field" + ("" if count == 1 else "s"),
                (row["_x"], row["_y"]),
                textcoords="offset points",
                xytext=(offset_x, offset_y),
                ha=horizontal_alignment,
                fontsize=6.0,
                color="#1a1a1a",
                zorder=5,
                clip_on=False,
                path_effects=_LABEL_HALO,
            )
        _panel_title(ax, grower, subset["field_id"].nunique())
    colorbar = fig.colorbar(
        ScalarMappable(norm=norm, cmap=cmap),
        ax=list(axes),
        orientation="horizontal",
        fraction=0.05,
        pad=0.06,
        shrink=0.55,
    )
    colorbar.set_label("Mean annual precipitation (mm)")
    cell_counts = cells.groupby("grower_slug").size()
    count_text = ", ".join(
        f"{grower_label(grower)} {int(cell_counts[grower])}" for grower in growers
    )
    _figure_title(
        fig,
        "Five-year mean annual precipitation by weather cell",
        f"Bubbles are NASA POWER grid cells (fields per cell shown): {count_text}. "
        "Effective spatial replication is 3-4 cells per grower, far below 10 fields.",
    )
    fig.subplots_adjust(left=0.02, right=0.98, top=0.82, bottom=0.22, wspace=0.08)
    _save(fig, path, dpi)


BOUNDARY_LABELS = {
    "area_acres": "Area (acres)",
    "compactness": "Compactness",
    "convexity": "Convexity",
}
CROP_LABELS = {
    "corn_years": "Corn years",
    "soybean_years": "Soybean years",
    "crop_diversity": "Crop diversity",
    "continuous_years": "Longest continuous run",
}
WEATHER_LABELS = {
    "gdd_season": "Season GDD",
    "precip_annual": "Annual precipitation",
    "precip_growing": "Growing-season precipitation",
    "heat_days_30": "Heat days \u226530 \u00b0C",
    "frost_free_days": "Frost-free days",
    "dry_days": "Dry days",
}


def _p_text(p_value: float) -> str:
    if not np.isfinite(p_value):
        return "p=n/a"
    if p_value < 0.001:
        return "p<0.001"
    if p_value < 0.01:
        return f"p={p_value:.4f}"
    return f"p={p_value:.3f}"


def _stars(p_value: float) -> str:
    if not np.isfinite(p_value):
        return ""
    if p_value < 0.001:
        return "***"
    if p_value < 0.01:
        return "**"
    if p_value < 0.05:
        return "*"
    return ""


def plot_boundary_comparison(comparison: pd.DataFrame, path, dpi: int) -> None:
    """Heatmap of pairwise grower effects for each boundary metric."""
    pairwise = comparison.loc[comparison["analysis"] == "mann-whitney-u"].copy()
    if pairwise.empty:
        return
    pairwise["pair"] = [
        f"{grower_label(first)}\u2013{grower_label(second)}"
        for first, second in zip(pairwise["group_a"], pairwise["group_b"])
    ]
    pairs = sorted(pairwise["pair"].unique(), key=natural_key)
    metrics = [metric for metric in BOUNDARY_LABELS if metric in set(pairwise["metric"])]
    effects = np.full((len(metrics), len(pairs)), np.nan)
    pvalues = np.full((len(metrics), len(pairs)), np.nan)
    for _, row in pairwise.iterrows():
        row_index = metrics.index(row["metric"])
        column_index = pairs.index(row["pair"])
        effects[row_index, column_index] = float(row["effect_size_rank_biserial"])
        pvalues[row_index, column_index] = float(row["p_bh"])

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    image = ax.imshow(effects, cmap="RdBu_r", vmin=-1.0, vmax=1.0, aspect="auto")
    for row_index in range(len(metrics)):
        for column_index in range(len(pairs)):
            effect = effects[row_index, column_index]
            if not np.isfinite(effect):
                continue
            color = "white" if abs(effect) > 0.6 else "#1a1a1a"
            ax.text(
                column_index,
                row_index,
                f"{effect:+.2f}\n{_p_text(pvalues[row_index, column_index])}",
                ha="center",
                va="center",
                fontsize=8,
                color=color,
                linespacing=1.25,
            )
    ax.set_xticks(range(len(pairs)))
    ax.set_xticklabels(pairs)
    ax.set_yticks(range(len(metrics)))
    ax.set_yticklabels([BOUNDARY_LABELS[metric] for metric in metrics])
    ax.set_xlabel("Grower pair (first vs second)")
    ax.tick_params(length=0)
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.03)
    colorbar.set_label("Rank-biserial effect", fontsize=7.5)
    colorbar.ax.tick_params(labelsize=7)

    significant = [
        BOUNDARY_LABELS[metric]
        for metric in metrics
        if np.any(pvalues[metrics.index(metric)] < 0.05)
    ]
    subtitle = (
        "Cells: rank-biserial effect and BH-adjusted p; negative means the first "
        "grower's fields are larger. BH-significant pairs: "
        + (", ".join(lower_first(label) for label in significant) if significant else "none")
        + "."
    )
    _figure_title(fig, "Pairwise boundary differences", _wrapped(subtitle))
    fig.subplots_adjust(left=0.14, right=0.98, top=0.84, bottom=0.17)
    _save(fig, path, dpi)


def _transition_residuals(transitions: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    table = transitions.pivot_table(
        index="grower_slug",
        columns="transition",
        values="count",
        aggfunc="sum",
        fill_value=0,
    )
    table = table.reindex(sorted(table.index))
    table = table[sorted(table.columns, key=natural_key)]
    observed = table.to_numpy(dtype=float)
    total = observed.sum()
    expected = (
        np.outer(observed.sum(axis=1), observed.sum(axis=0)) / total
        if total
        else np.zeros_like(observed)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        residuals = (observed - expected) / np.sqrt(expected)
    return table, residuals


def plot_crop_comparison(
    comparison: pd.DataFrame, transitions: pd.DataFrame, path, dpi: int
) -> None:
    """Rotation effect sizes plus a transition observed-vs-expected heatmap."""
    tests = comparison.loc[comparison["analysis"] == "kruskal-wallis"].copy()
    metrics = [metric for metric in CROP_LABELS if metric in set(tests["metric"])]
    figure, (left, right) = plt.subplots(
        1,
        2,
        figsize=(10.8, 4.4),
        gridspec_kw={"width_ratios": [0.9, 1.2]},
    )

    values = []
    pvalues = []
    for metric in metrics:
        row = tests.loc[tests["metric"] == metric].iloc[0]
        values.append(float(row["effect_size_epsilon_sq"]))
        pvalues.append(float(row["p_value"]))
    positions = np.arange(len(metrics))
    colors = ["#D55E00" if p < 0.05 else "#0072B2" for p in pvalues]
    left.barh(positions, values, color=colors, height=0.6, alpha=0.9)
    for position, value, p_value in zip(positions, values, pvalues):
        left.text(
            value + 0.006,
            position,
            f"epsilon-squared={value:.2f}  {_p_text(p_value)}",
            va="center",
            fontsize=7.5,
            color="#1a1a1a",
        )
    left.set_yticks(positions)
    left.set_yticklabels([CROP_LABELS[metric] for metric in metrics])
    left.invert_yaxis()
    left.set_xlim(0.0, max(0.30, max(values, default=0.0) * 2.0))
    left.set_xlabel("Kruskal-Wallis epsilon-squared")
    left.set_title("Rotation metric effect sizes", loc="left", fontweight="bold", pad=10)
    left.grid(axis="y", visible=False)

    table, residuals = _transition_residuals(transitions)
    limit = max(2.0, float(np.nanmax(np.abs(residuals))) if residuals.size else 2.0)
    image = right.imshow(
        residuals, cmap="RdBu_r", vmin=-limit, vmax=limit, aspect="auto"
    )
    observed = table.to_numpy(dtype=float)
    for row_index in range(residuals.shape[0]):
        for column_index in range(residuals.shape[1]):
            residual = residuals[row_index, column_index]
            if not np.isfinite(residual):
                continue
            color = "white" if abs(residual) > 0.6 * limit else "#1a1a1a"
            right.text(
                column_index,
                row_index,
                f"{int(observed[row_index, column_index])}\n{residual:+.1f}",
                ha="center",
                va="center",
                fontsize=8,
                color=color,
                linespacing=1.25,
            )
    right.set_xticks(range(len(table.columns)))
    right.set_xticklabels(
        [str(column).replace("->", "\u2192") for column in table.columns],
        rotation=12,
        ha="right",
    )
    right.set_yticks(range(len(table.index)))
    right.set_yticklabels([grower_label(index) for index in table.index])
    right.tick_params(length=0)
    right.grid(False)
    for spine in right.spines.values():
        spine.set_visible(False)
    right.set_title(
        "Transition mix: observed count / std. residual",
        loc="left",
        fontweight="bold",
        pad=10,
    )
    colorbar = figure.colorbar(image, ax=right, fraction=0.04, pad=0.03)
    colorbar.set_label("Std. residual (observed minus expected)", fontsize=7)
    colorbar.ax.tick_params(labelsize=7)

    continuous = tests.loc[tests["metric"] == "continuous_years"]
    if continuous.empty:
        continuous_text = "longest continuous run"
    else:
        row = continuous.iloc[0]
        continuous_text = (
            f"longest continuous run (epsilon-squared="
            f"{float(row['effect_size_epsilon_sq']):.2f}, "
            f"{_p_text(float(row['p_value']))})"
        )
    chi = comparison.loc[comparison["analysis"] == "chi-square"]
    chi_text = "transition mix"
    if not chi.empty:
        row = chi.iloc[0]
        chi_text = (
            f"transition mix (chi-square {_p_text(float(row['p_value']))}, "
            f"Cramer's V={float(row['effect_size_cramers_v']):.2f})"
        )
    story = f"Growers differ in {continuous_text} and {chi_text}"
    if residuals.size:
        row_index, column_index = np.unravel_index(
            int(np.nanargmax(residuals)), residuals.shape
        )
        story += (
            f"; {grower_label(table.index[row_index])} over-represents "
            f"{str(table.columns[column_index]).replace('->', 'to').strip()}"
        )
    _figure_title(
        figure,
        "Crop rotation and transition comparisons",
        _wrapped(story + "."),
    )
    figure.subplots_adjust(left=0.15, right=0.97, top=0.80, bottom=0.17, wspace=0.55)
    _save(figure, path, dpi)


def plot_weather_comparison(comparison: pd.DataFrame, path, dpi: int) -> None:
    """Dumbbell chart of field-level and weather-cell-level effect sizes."""
    table = comparison.pivot_table(
        index="metric",
        columns="level",
        values="effect_size_epsilon_sq",
        aggfunc="first",
    )
    if table.empty or not {"field", "weather-cell"} <= set(table.columns):
        return
    rows = []
    for metric in WEATHER_LABELS:
        if metric not in table.index:
            continue
        field_value = float(table.at[metric, "field"])
        cell_value = float(table.at[metric, "weather-cell"])
        if np.isfinite(field_value) and np.isfinite(cell_value):
            rows.append((metric, field_value, cell_value))
    if not rows:
        return

    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    handles = []
    for position, (metric, field_value, cell_value) in enumerate(rows):
        ax.plot(
            [field_value, cell_value],
            [position, position],
            color="#999999",
            linewidth=1.6,
            zorder=1,
        )
        field_point = ax.scatter(
            field_value,
            position,
            s=70,
            color="#0072B2",
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
            label="Field-level test",
        )
        cell_point = ax.scatter(
            cell_value,
            position,
            s=70,
            color="#D55E00",
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
            label="Weather-cell test",
        )
        if position == 0:
            handles = [field_point, cell_point]
        if field_value <= cell_value:
            field_offset, field_align = -7.0, "right"
            cell_offset, cell_align = 7.0, "left"
        else:
            field_offset, field_align = 7.0, "left"
            cell_offset, cell_align = -7.0, "right"
        ax.annotate(
            f"{field_value:.2f}",
            (field_value, position),
            textcoords="offset points",
            xytext=(field_offset, 0),
            ha=field_align,
            va="center",
            fontsize=7.5,
            color="#0072B2",
        )
        ax.annotate(
            f"{cell_value:.2f}",
            (cell_value, position),
            textcoords="offset points",
            xytext=(cell_offset, 0),
            ha=cell_align,
            va="center",
            fontsize=7.5,
            color="#D55E00",
        )
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([WEATHER_LABELS[metric] for metric, _, _ in rows])
    ax.invert_yaxis()
    ax.set_xlim(0.0, 1.0)
    ax.set_xticks([0.0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("Kruskal-Wallis epsilon-squared (higher = growers differ more)")
    ax.legend(handles=handles, loc="lower right", frameon=False)
    ax.grid(axis="y", visible=False)

    gdd = next((row for row in rows if row[0] == "gdd_season"), None)
    max_drop = max(rows, key=lambda row: row[1] - row[2])
    subtitle = ""
    if gdd is not None:
        subtitle = (
            f"GDD separates growers most strongly at both levels "
            f"(epsilon-squared={gdd[1]:.2f} field, {gdd[2]:.2f} cell). "
        )
    if max_drop[1] - max_drop[2] > 0.02:
        subtitle += (
            f"The largest field-to-cell drop is {max_drop[1] - max_drop[2]:.2f} for "
            f"{lower_first(WEATHER_LABELS[max_drop[0]])}; shared NASA POWER cells do not "
            "explain the grower gaps."
        )
    else:
        subtitle += (
            "Effect sizes are stable when fields are collapsed to cells, so shared "
            "NASA POWER cells do not explain the grower gaps."
        )
    _figure_title(
        fig, "Weather separation at field and grid-cell level", _wrapped(subtitle)
    )
    fig.subplots_adjust(left=0.24, right=0.98, top=0.84, bottom=0.14)
    _save(fig, path, dpi)


def plot_weather_correlations(correlations: pd.DataFrame, path, dpi: int) -> None:
    """Spearman correlation matrix of the seasonal weather metrics."""
    if correlations.empty:
        return
    present = set(correlations["var_a"]) | set(correlations["var_b"])
    variables = [metric for metric in WEATHER_LABELS if metric in present]
    size = len(variables)
    if size < 2:
        return
    rho = np.full((size, size), np.nan)
    pvalues = np.full((size, size), np.nan)
    np.fill_diagonal(rho, 1.0)
    np.fill_diagonal(pvalues, 0.0)
    for _, row in correlations.iterrows():
        first = variables.index(row["var_a"]) if row["var_a"] in variables else None
        second = variables.index(row["var_b"]) if row["var_b"] in variables else None
        if first is None or second is None:
            continue
        rho[first, second] = rho[second, first] = float(row["rho"])
        pvalues[first, second] = pvalues[second, first] = float(row["p_bh"])

    lower = np.tril(np.ones_like(rho), k=-1).astype(bool)
    masked = np.ma.array(rho, mask=lower)
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    image = ax.imshow(masked, cmap="RdBu_r", vmin=-1.0, vmax=1.0, aspect="auto")
    for row_index in range(size):
        for column_index in range(row_index, size):
            value = rho[row_index, column_index]
            if not np.isfinite(value):
                continue
            color = "white" if abs(value) > 0.6 else "#1a1a1a"
            stars = "" if row_index == column_index else _stars(
                pvalues[row_index, column_index]
            )
            ax.text(
                column_index,
                row_index,
                f"{value:.2f}{stars}",
                ha="center",
                va="center",
                fontsize=8.5,
                color=color,
                fontweight="bold" if abs(value) >= 0.6 else "normal",
            )
    ax.set_xticks(range(size))
    ax.set_xticklabels(
        [WEATHER_LABELS[variable] for variable in variables], rotation=28, ha="right"
    )
    ax.set_yticks(range(size))
    ax.set_yticklabels([WEATHER_LABELS[variable] for variable in variables])
    ax.tick_params(length=0)
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.04, pad=0.03)
    colorbar.set_label("Spearman rho", fontsize=8)
    colorbar.ax.tick_params(labelsize=7)

    positive = correlations.loc[correlations["rho"].idxmax()]
    negative = correlations.loc[correlations["rho"].idxmin()]
    subtitle = (
        f"{WEATHER_LABELS[positive['var_a']]} and "
        f"{lower_first(WEATHER_LABELS[positive['var_b']])} move together "
        f"(rho={positive['rho']:.2f}); "
        f"{lower_first(WEATHER_LABELS[negative['var_a']])} and "
        f"{lower_first(WEATHER_LABELS[negative['var_b']])} move oppositely "
        f"(rho={negative['rho']:.2f})."
    )
    _figure_title(
        fig, "Weather metric correlations (all field-years)", _wrapped(subtitle)
    )
    fig.text(
        0.01,
        0.012,
        "Stars: BH-adjusted p (* <0.05, ** <0.01, *** <0.001). Lower triangle masked.",
        fontsize=7.5,
        color="#555555",
        ha="left",
        va="bottom",
    )
    fig.subplots_adjust(left=0.30, right=0.96, top=0.82, bottom=0.22)
    _save(fig, path, dpi)
