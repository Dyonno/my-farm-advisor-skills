# Field-Level EDA Guide

This guide explains the workflow, the statistical choices, and the story each
figure and comparison table is meant to tell. Run the workflow from
`../README.md`; this file focuses on interpretation.

## Analysis structure

The workflow compares three things at three scales:

| Scale | Boundary | Crop history | Weather |
| --- | --- | --- | --- |
| Within a field over time | — | rotation sequence and stability | cumulative GDD and seasonal metrics |
| Across fields in a grower | area, shape, compactness | composition and rotation mix | field-level distributions |
| Across growers | Kruskal-Wallis and pairwise tests | transition chi-square | field-level and grid-cell tests |

Every category has two distribution figures plus one comparison or correlation
table, and each comparison or correlation test also has a dedicated figure
(10-13). All tests are nonparametric because each grower has only 10 fields.

## Boundary analysis

### Figure 01 — Field size by grower

Box plots with every field overlaid.

**Story:** IA and IL have nearly identical median field size (600 and 606
acres). NE fields are about 15% smaller (514 acres). Kruskal-Wallis
p = 0.00011, epsilon-squared = 0.60, so grower identity explains most of the
rank variation. Pairwise Mann-Whitney confirms IA vs IL is not distinguishable
(p = 0.97) while both differ from NE (BH-adjusted p < 0.001).

**Why it matters:** field size drives equipment passes, headland area, and the
cost of per-field operations. Treating NE as a smaller-field operation is
supported; treating IA and IL as different size classes is not.

### Figure 02 — Shape regularity vs field size

Polsby-Popper compactness against area, with the three least compact and three
largest fields labelled.

**Story:** field size weakly predicts compactness (Spearman rho = -0.33,
p = 0.08). Compactness itself does not differ by grower (Kruskal-Wallis
p = 0.69), but IL fields carry the most boundary vertices (median 157 versus 89
in IA and 102 in NE) and the lowest median convexity (0.80). Shape complexity is
therefore a within-IL feature, not a simple consequence of larger fields.

**Why it matters:** low compactness and many vertices mean more edge per acre,
which affects headlands, fencing, and sensing coverage. Inspect IL fields before
assuming a rectangular-field workflow.

### Figure 03 — Demo farm field layout

One panel per grower, each zoomed to its own fields with county context. Labels
are shortened field IDs (`r1`, `r10`).

**Story:** each grower's 10 fields sit in one county, and the three clusters are
far apart (Iroquois County IL, Kossuth County IA, York County NE). Panel scale
differs by design, so compare shapes and arrangement within a panel, not absolute
field size across panels.

**Why it matters:** the growers are not neighbors. Any cross-grower comparison
is a state/climate comparison, not a within-neighborhood comparison.

### Boundary comparison table

`boundary_comparison.csv` combines:

- Kruskal-Wallis for area, compactness, and convexity by grower.
- Pairwise Mann-Whitney U with rank-biserial effect sizes and BH-adjusted
  p-values.

Use `median_a`, `median_b`, and `effect_size_rank_biserial` to describe
direction; do not read the p-value alone.

## Crop-history analysis

Crop composition is recomputed from `pixel_count` so each field-year sums to
100%. Raw CDL classes are collapsed into Corn, Soybeans, Small grains, Forage,
Pasture/Grass, Fallow/Idle, and Other/Non-crop. `crop_dominant.csv` keeps the raw
class name.

### Figure 04 — Crop composition by field and year

100% stacked horizontal bars for every field-year, one panel per grower-year.

**Story:** corn and soybeans account for 98.9% of CDL pixels. The remaining
classes are thin field-edge slivers, not whole fields. Composition is stable
within a grower; changes between years are swaps between corn and soybeans.

**Why it matters:** field-level CDL supports a two-crop rotation model. Analyses
that treat the non-crop share as a meaningful land-use class would overstate it.

### Figure 05 — Within-field rotation, 2019-2023

Heatmap of the dominant crop group per field-year. Rows are fields, blocks are
growers, and letters are C (corn), S (soybeans), W (small grains), F (forage),
P (pasture), I (fallow), and O (other).

**Story:** continuous corn is concentrated in NE: 3 of 10 fields, versus 1 of 10
in IL and 0 of 10 in IA. The other fields alternate corn and soybeans. The
transition chi-square is significant (p = 0.0002, Cramer's V = 0.30), and mean
continuous years differ (Kruskal-Wallis p = 0.047, epsilon-squared = 0.15).
Corn-year counts alone are not significant (p = 0.11) because the NE signal is
carried by a few fields rather than a shift of every field.

**Why it matters:** within-field rotation is the clearest agronomic difference
between the growers. NE's continuous-corn blocks are candidates for resistance,
nutrient, and soil-health review.

### Figure 06 — Dominant crop in 2023

One panel per grower, colored by the dominant crop group in the last CDL year.

**Story:** the 2023 CDL class matches the grower-reported field crop for all 30
fields. IL is corn-heavy in 2023 (8 of 10 fields), IA is soybean-heavy (7 of
10), and NE is an even split. This is a snapshot of the rotation heatmap's final
column, not independent evidence.

**Why it matters:** it validates that the CDL processing is aligned with the
field inventory, and it gives a simple map for stakeholder review.

### Crop comparison tables

- `crop_comparison.csv`: Kruskal-Wallis for corn years, soybean years, crop
  diversity, and continuous years, plus the transition chi-square.
- `crop_transitions.csv`: counts for every from-group/to-group transition.
- `crop_rotation_summary.csv`: per-field sequence, diversity, continuous years,
  and a check against the pipeline's reported rotation sequence.

## Weather analysis

GDD uses the daily mean of `T2M_MAX` and `T2M_MIN`, base 10 °C, cap 30 °C, and
Apr 1-Sep 30. Frost metrics use `T2M_MIN <= 0 °C` with the last spring frost at
day-of-year 213 or earlier and the first fall frost after that.

### Figure 07 — Cumulative growing degree days

One panel per grower; thin lines are fields, thick lines are grower-year means.

**Story:** NE accumulates the most heat (mean seasonal GDD 2,068 versus 1,847 in
IL and 1,723 in IA). At the same calendar date, NE is further along in crop
development. Kruskal-Wallis p = 3.4e-25 at field level (epsilon-squared = 0.75)
and p = 1.7e-8 at the weather-cell level (epsilon-squared = 0.72), so the result
survives the shared-cell correction.

**Why it matters:** planting-date, scouting, and harvest-timing advice should
not be transferred directly between these growers on the calendar alone.

### Figure 08 — Monthly precipitation climatology

Five-year mean monthly precipitation per NASA POWER grid cell, with observed
min-max whiskers and the Apr-Sep growing season shaded.

**Story:** IA peaks in June-August; IL carries more rain in spring and fall; NE
is the driest overall (610 mm/year versus 775 in IA and 917 in IL). Growing
season totals are 564 mm (IA), 535 mm (IL), and 446 mm (NE). The wide whiskers
show that interannual variability is large relative to the grower differences.

**Why it matters:** irrigation and drainage questions depend on both the total
and its timing. NE's lower and more variable supply is a planning risk.

### Figure 09 — Mean annual precipitation by weather cell

Each bubble is a distinct NASA POWER grid cell; bubble size is the number of
fields sharing it, and the label gives that count.

**Story:** the 30 fields collapse to 3 cells in IA, 4 in IL, and 3 in NE. Cells
hold 1-8 fields. Effective spatial replication is 3-4 per grower, not 10, so
field-level weather p-values are optimistic. The cell-level tests are the
conservative read.

**Why it matters:** any model that treats field weather as independent will
overstate confidence. Aggregate to cells or use a mixed model before drawing
inference beyond this demo.

### Weather comparison and correlation tables

- `weather_comparison.csv`: Kruskal-Wallis for GDD, annual and growing-season
  precipitation, heat days ≥30 °C, and frost-free days, repeated at field and
  weather-cell level.
- `weather_correlations.csv`: Spearman correlations among seasonal metrics with
  BH-adjusted p-values. Strong pairs in the demo: GDD vs heat days (rho = 0.84),
  annual precipitation vs heat days (rho = -0.84), annual vs growing-season
  precipitation (rho = 0.71), and GDD vs annual precipitation (rho = -0.56).
- `weather_seasonal_metrics.csv`: field-year metrics behind the figures.
- `weather_cells.csv`: field-to-cell map and cell identifiers.

## Comparison and correlation figures

These four figures turn the comparison tables into effect-size views. They are
the quickest way to see which differences are large enough to act on.

### Figure 10 — Pairwise boundary effects

Heatmap of metric by grower pair. Cell color and the top number are the
rank-biserial effect from the Mann-Whitney test; the second number is the
BH-adjusted p-value. Negative means the first grower in the pair has larger
values.

**Story:** area is the only boundary metric that separates growers. IA and IL are
indistinguishable (r = -0.02, p = 0.97), while NE fields are smaller than both
(IA vs NE r = -1.00, IL vs NE r = -0.94, both BH p < 0.001). Compactness effects
stay within |r| = 0.20 and convexity within |r| = 0.52; no shape pair survives BH
correction (smallest p = 0.16).

**Why it matters:** size differences are consistent enough to plan around; shape
differences are field-specific. Do not build a grower-level shape rule from this
demo.

### Figure 11 — Rotation effects and transition mix

Left: Kruskal-Wallis epsilon-squared for the four rotation metrics, with
significant effects in orange. Right: grower by transition heatmap showing the
observed count and the standardized Pearson residual (observed minus expected,
divided by the square root of expected).

**Story:** the longest continuous run is the only rotation metric that separates
growers (epsilon-squared = 0.15, p = 0.047); corn years, soybean years, and crop
diversity all sit at p = 0.11-0.14. The transition heatmap localizes the signal:
NE records 16 corn-to-corn transitions against about 7 expected (residual +3.4),
while IA records 1 (-2.3) and IL 4 (-1.1). The overall transition chi-square is
p < 0.001 with Cramer's V = 0.30.

**Why it matters:** aggregate rotation counts dilute a practice that is
concentrated in a few NE fields. Continuous-corn review should start from the
transition residuals and the figure 05 field list, not from grower means.

### Figure 12 — Weather effects at field and cell level

Dumbbell chart with one row per weather metric. Blue is the field-level
Kruskal-Wallis epsilon-squared; orange is the same test after collapsing fields
to distinct NASA POWER cells.

**Story:** the ranking is stable. GDD separates growers most strongly (0.75 field,
0.72 cell), followed by heat days (0.66, 0.62) and annual precipitation (0.50,
0.52). Growing-season precipitation and frost-free days are weaker (0.17-0.25).
The largest field-to-cell drop is 0.06 for frost-free days, and no metric loses
its ordering.

**Why it matters:** the grower climate gaps are spatial, not an artifact of
treating fields in one grid cell as independent. Cell-level effects remain the
conservative number to quote.

### Figure 13 — Weather correlation matrix

Spearman rho for every pair of seasonal metrics across all 150 field-years. The
lower triangle is masked; stars mark BH-adjusted significance.

**Story:** the metrics organize into a heat axis and a moisture axis. GDD and heat
days rise together (rho = 0.84), and both fall as precipitation rises (GDD vs
annual precipitation rho = -0.56; heat days vs annual precipitation rho = -0.84).
Annual and growing-season precipitation agree at rho = 0.71, and dry days track
low precipitation (growing-season precipitation vs dry days rho = -0.67). Frost
is nearly independent of heat (rho = 0.11) and moisture (-0.06); those are the
only two pairs that do not survive BH correction (13 of 15 do).

**Why it matters:** one "climate score" would mix two separate gradients. Rank
growers on heat and moisture separately, and avoid using frost-free days as a
proxy for either. The correlations pool field-years, and weather repeats within
grid cells, so treat rho as descriptive rather than cell-level inference.

## Reading the outputs together

- Boundary and weather both separate NE, but for different reasons: smaller
  fields and a hotter, drier climate.
- Rotation separates NE even more sharply than field size; continuous corn is
  the distinctive practice.
- IL is not a copy of IA. Field size and climate are similar, but IL has more
  boundary complexity and more spring/fall precipitation.
- No table links crop-year weather to crop-year CDL because the windows differ
  (CDL 2019-2023, weather 2021-2025). Add a paired-year extract before making
  yield or management claims.

## Reproducing and extending

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/runtime/root
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  data-pipeline/src/scripts/run_field_eda.py --dry-run
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  data-pipeline/src/scripts/run_field_eda.py
```

Add a category by creating a module that returns tidy per-field/per-year
metrics and a comparison frame, then wire it into `src/field_eda.py` and add its
tables and figures to `TABLE_FILENAMES` and `figure_specs`. Keep the statistical
helpers in `eda_stats.py` so effect sizes and multiple-comparison handling stay
consistent.

## Caveats

- Ten fields per grower is a demo, not a survey. Treat p-values as exploratory.
- CDL pixel shares include field-edge mixing; the non-crop share is not a
  land-use estimate.
- GDD is a simple daily-average formula, not a crop-specific model.
- Frost dates use a fixed 0 °C threshold and day-of-year split; sensitive crops
  may need a different threshold.
- Weather cells are inferred from identical daily series. Coincident series
  across distant cells are unlikely here but would be misclassified.
