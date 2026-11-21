# Field-Level EDA Examples

## Smoke run

From the repository root, with the runtime configured:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/runtime/root

# Show the discovered inputs without writing anything.
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  data-pipeline/src/scripts/run_field_eda.py --dry-run

# Single grower for a quick check.
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  data-pipeline/src/scripts/run_field_eda.py \
  --grower il-demo-grower \
  --output-dir "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda-smoke"

# Full three-grower run (default output).
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  data-pipeline/src/scripts/run_field_eda.py
```

Expected for the full demo dataset:

- 30 fields, 3 growers, 17,873 acres
- 15 tables and 13 figures
- 1 manifest at `eda/field-eda/manifest.json`

## Output tree

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda/
├── manifest.json
├── tables/
│   ├── field_boundary_metrics.csv
│   ├── boundary_comparison.csv
│   ├── boundary_grower_summary.csv
│   ├── crop_composition.csv
│   ├── crop_dominant.csv
│   ├── crop_rotation_summary.csv
│   ├── crop_transitions.csv
│   ├── crop_comparison.csv
│   ├── crop_grower_summary.csv
│   ├── weather_seasonal_metrics.csv
│   ├── weather_comparison.csv
│   ├── weather_grower_summary.csv
│   ├── weather_correlations.csv
│   ├── weather_cells.csv
│   └── field_profile.csv
└── figures/
    ├── 01_field_size_by_grower.png
    ├── 02_shape_vs_area.png
    ├── 03_field_map.png
    ├── 04_crop_composition.png
    ├── 05_rotation_heatmap.png
    ├── 06_crop_map_2023.png
    ├── 07_gdd_curves.png
    ├── 08_monthly_precip.png
    ├── 09_weather_map.png
    ├── 10_boundary_comparison_effects.png
    ├── 11_crop_comparison_effects.png
    ├── 12_weather_comparison_effects.png
    └── 13_weather_correlation_matrix.png
```

Generated outputs are runtime artifacts and must stay out of Git. The
`field_profile.csv` table is the easiest inspection point: one row per field with
boundary, 2023 crop, rotation, and climate columns.

## Checking a run

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["DATA_PIPELINE_DATA_ROOT"]) / "data-pipeline/eda/field-eda"
manifest = json.loads((root / "manifest.json").read_text())
print(manifest["headline"])
print(len(manifest["tables"]), "tables", len(manifest["figures"]), "figures")
PY
```

A healthy run reports 3 growers, 30 fields, 15 tables, and 13 figures. Check the
figure subtitles against `../GUIDE.md`; they carry the takeaway for each plot.
