# Assignment 2 field-level EDA report

This folder holds the one-time review report for the field-level EDA workflow.
It is deliberately outside the reusable subskill.

- **Report:** [`field-eda-report.pdf`](field-eda-report.pdf) — 13 pages, under 1 MB,
  rendered directly by GitHub from the pull request.
- **Builder:** [`build_report.py`](build_report.py) — regenerates the PDF from an
  existing field-eda run.
- **Skill:** [`my-farm-advisor/eda/field-eda/`](../../my-farm-advisor/eda/field-eda/)

## Report contents

| Section | Pages | Figures |
| --- | --- | --- |
| Cover and contents | 1 | — |
| Dataset scope, grower locations, data layers | 2 | `03` field layout |
| Comparison levels and methods, metric definitions | 3 | — |
| Boundary analysis | 4–5 | `01`, `02` |
| Crop-history analysis and rotation sequences | 6–7 | `04`, `05` |
| Weather analysis | 8 | `07`, `08` |
| Comparison and correlation analyses | 9–10 | `10`, `11`, `12`, `13` |
| Geospatial maps | 11 | `06`, `09` |
| Limitations, assumptions, missing data, soil scope | 12 | — |
| Artifact inventory and headline statistics | 13 | — |

All 13 figures and 15 tables from the source run are accounted for. The report
states the soil scope explicitly: soil analysis was not required, not performed,
and not part of the EDA.

## Source run

- Manifest generated: `2026-11-18T00:57:35Z`
- Growers: `il-demo-grower` (Iroquois County, IL), `ia-demo-grower` (Kossuth
  County, IA), `ne-demo-grower` (York County, NE)
- Scope: 3 growers, 3 farms, 30 fields, 17,873 acres
- Windows: CDL 2019–2023, weather 2021–2025
- Outputs: 15 CSV tables, 13 PNG figures, `manifest.json`

The runtime folder is not committed. Only this PDF, its builder, and these notes
are tracked; tables, figures, and the manifest stay under
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda/`.

## Rebuild

From the repository root, with the runtime root that holds a completed
`field-eda` run:

```bash
DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime \
  /path/to/my-farm-advisor-runtime/data-pipeline/.venv/bin/python \
  reports/assignment-2-field-eda/build_report.py
```

Optional flags: `--eda-dir` to point at a different run directory and
`--output` to write a different PDF path. The builder needs `pandas` and
`Pillow`; it fails loudly when the manifest, tables, or figures are missing.

The PDF is a snapshot of the run named above, not a live dashboard. Rebuild it
when the underlying EDA outputs change, then re-check the size stays under 1 MB
so the file remains normally tracked and previewable in the pull request.

## Validation

```bash
./scripts/validate.sh
```
