# Local Instructions

## Purpose

`eda/field-eda/` owns the reusable field-level EDA workflow for My Farm Advisor:
boundary metrics, CDL crop history, and weather comparisons across growers.

## Safe edit scope

Stay inside `eda/field-eda/` except for the runtime entrypoint
`data-pipeline/src/scripts/run_field_eda.py` and the `eda/INDEX.md` routing link.
Do not change the umbrella `SKILL.md`, sibling EDA workflows, or root policy
from a subskill task unless explicitly requested.

## Contract

- Inputs are read from the configured runtime root; never hard-code a checkout
  or `/tmp` data path.
- Outputs are static CSV/PNG plus `manifest.json`. Do not add a dashboard, web
  map, or report generator here. Report assembly is a separate one-time artifact.
- Do not add soil inputs or soil analysis; this subskill deliberately excludes
  them.
- Keep `src/field_eda.py` as orchestration. Put metrics, statistics, and
  plotting in the sibling modules so they stay reusable and testable.
- Preserve `pixel_count` denominators for crop composition. The rounded `pct`
  column is display-only.
- Keep weather comparisons at both field and NASA POWER cell level so shared
  cells are visible in the results.

## Read nearby docs first

Read `README.md` and `GUIDE.md`. For routing context, read `../INDEX.md` and
`../../SKILL.md`.

## Local validation

Run the repository validator from the repo root:

```bash
./scripts/validate.sh
```

Then run the smoke command in `examples/README.md` against the smallest
available grower set and confirm the manifest, 15 tables, and 13 figures are
written. Generated outputs stay under the runtime root and out of Git.
