# Field-Level EDA

Static exploratory analysis that compares field boundaries, CDL crop history, and
NASA POWER weather for the demo growers. It answers three questions:

1. How do fields differ **within** a field over time?
2. How do fields differ **across fields** inside one grower?
3. How do growers differ **across the three states**?

The subskill produces plain CSV tables and PNG figures. It does not build a
report, dashboard, or web map; a downstream report can consume the manifest.

## Layout

```text
eda/field-eda/
├── src/
│   ├── eda_stats.py          # BH correction, Kruskal-Wallis, Mann-Whitney, chi-square, Spearman
│   ├── boundary_metrics.py   # area, perimeter, compactness, convexity, tests
│   ├── crop_history.py       # crop groups, composition shares, rotations, transitions
│   ├── weather_metrics.py    # GDD, frost, precipitation, weather-cell detection, tests
│   ├── eda_plots.py          # thirteen static matplotlib figures
│   ├── field_eda.py          # orchestration, table/figure writes, manifest
│   └── __init__.py
├── examples/README.md        # smoke command and expected output tree
├── GUIDE.md                  # methods, outputs, and the story for each figure
└── AGENTS.md                 # local scope guardrails
```

## Inputs

Per grower/farm under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/`:

- `boundary/field_boundaries.geojson` — field polygons with `field_id`, `crop`,
  `state`, `county`, and `state_fips`.
- `derived/tables/<prefix>_weather_<start>_<end>.csv` — daily weather with
  `field_id`, `date`, `T2M`, `T2M_MAX`, `T2M_MIN`, `PRECTOTCORR`,
  `ALLSKY_SFC_SW_DWN`, `RH2M`, `WS10M`.
- `derived/tables/<prefix>_cdl_<start>_<end>_full_composition.csv` — CDL
  `field_id`, `year`, `crop_code`, `crop_name`, `pixel_count`, `pct`.
- `derived/tables/<prefix>_crop_rotation.csv` — optional; used only to check
  that the EDA rotation sequence matches the pipeline's reported sequence.

County context is optional: `shared/geoadmin/l2_counties/counties_usa.parquet`.
Run without it using `--no-counties`.

## Run

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/runtime/root
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  data-pipeline/src/scripts/run_field_eda.py
```

The CLI discovers every grower/farm with complete boundary, weather, and CDL
inputs. Limit the run with `--grower il-demo-grower --grower ia-demo-grower` or
inspect the plan first with `--dry-run`.

Defaults:

- Output: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda/`
- CDL years: 2019-2023
- Weather years: 2021-2025
- GDD base 10 °C, cap 30 °C, growing season Apr 1-Sep 30
- 200 dpi PNG figures

## Outputs

`tables/` contains 15 CSVs:

| Table | Grain | Purpose |
| --- | --- | --- |
| `field_boundary_metrics.csv` | field | area, perimeter, compactness, convexity, vertices, centroid |
| `boundary_comparison.csv` | test | Kruskal-Wallis plus pairwise Mann-Whitney with BH-adjusted p-values |
| `boundary_grower_summary.csv` | grower | median area/shape and within-grower spread |
| `crop_composition.csv` | field-year-class | shares recomputed from `pixel_count` |
| `crop_dominant.csv` | field-year | dominant crop group and raw CDL class |
| `crop_rotation_summary.csv` | field | five-year sequence, diversity, continuous years |
| `crop_transitions.csv` | grower-transition | consecutive-year transition counts |
| `crop_comparison.csv` | test | rotation Kruskal-Wallis plus transition chi-square |
| `crop_grower_summary.csv` | grower | mean corn/soybean years and continuous-corn counts |
| `weather_seasonal_metrics.csv` | field-year | GDD, precipitation, heat days, frost metrics |
| `weather_comparison.csv` | test | field-level and weather-cell-level Kruskal-Wallis |
| `weather_grower_summary.csv` | grower | climate summary and cell counts |
| `weather_correlations.csv` | pair | Spearman correlations with BH-adjusted p-values |
| `weather_cells.csv` | field | shared NASA POWER cell assignment |
| `field_profile.csv` | field | joined boundary, 2023 crop, rotation, and climate profile |

`figures/` contains thirteen PNGs, described in `GUIDE.md`. Figures 01-09 show
distributions, rotations, and maps; figures 10-13 visualize each comparison and
correlation test.

`manifest.json` records parameters, input paths and row counts, table/figure
checksums, and headline test results. Generated outputs live outside Git.

## Methods

- Geometry is measured in EPSG:5070 (Conus Albers, equal area), so acreage,
  perimeter, and compactness are comparable across states.
- Compactness is Polsby-Popper: `4π·area / perimeter²` (1 = circle).
- Crop composition uses `pixel_count` as the denominator, not the rounded `pct`
  column, so every field-year sums to 100%.
- CDL classes are collapsed to seven groups; `crop_dominant.csv` preserves the
  raw class name for traceability.
- Weather tests run twice: once per field and once per distinct NASA POWER grid
  cell. Several fields share one cell, so field-level n overstates independent
  replication.
- Tests are nonparametric and exploratory (10 fields per grower): Kruskal-Wallis,
  pairwise Mann-Whitney, chi-square, and Spearman. Results include effect sizes
  and BH-adjusted p-values where multiple comparisons are made.

## Scope notes

- No soil analysis is required or performed.
- Report generation is intentionally out of scope. The manifest is the handoff.
- The subskill is reusable, but the demo farm paths are resolved by the
  data-pipeline CLI so inputs stay under the configured runtime root.
