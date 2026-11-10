# Grower Web Map Local Instructions

## Purpose

Render lightweight interactive HTML maps from the field polygons already produced
by the data pipeline: one combined map across growers plus one map per grower.
This folder documents the subskill; the implementation lives in
[`../src/scripts/render_grower_web_map.py`](../src/scripts/render_grower_web_map.py).

## Safe edit scope

Keep changes inside `data-pipeline/grower-web-map/` and
`data-pipeline/src/scripts/render_grower_web_map.py`. Do not change parent
`SKILL.md`, sibling workflows, or root policy from this subskill.

## Read nearby docs first

Read `README.md`, then `../AGENTS.md` for the runtime contract, then the
implementation script.

## Operating rules

- Read the pipeline's `field_boundaries.geojson` as the only geometry source.
  Never re-fetch or re-derive field boundaries here.
- Embed fields as real GeoJSON `Feature` objects (`type`, `geometry`,
  `properties`), never as loose records: Leaflet's `L.geoJSON` throws
  `Invalid GeoJSON object` on anything else and the page dies before it can fit
  the view, which renders a blank grey map.
- Give the Leaflet map an explicit `setView` before layers load, and keep the
  `try/catch` error banner around initialisation so failures are visible instead
  of silent.
- The HTML may reference online basemap tiles (ESRI World Imagery only) but must
  not embed rasters, imagery, NDVI, DEM, or full data bundles.
- Keep the embedded payload to boundary coordinates only; round coordinates to
  six decimal places and simplify only when the operator passes
  `--simplify-tolerance`.
- Write only under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/`: the combined map
  in `maps/`, the combined manifest in `manifests/`, and per-grower outputs under
  `growers/<grower>/`. Never write generated maps into the skill checkout or
  commit them.
- Keep output deterministic: sort growers, farms, and fields, use stable colors
  by index, and keep timestamps out of the HTML (the manifest may carry
  `generated_at`).

## Command runbook

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/render_grower_web_map.py --grower-slug <grower-slug>
```

Omitting `--grower-slug` renders every grower into the combined map plus one map
per grower. Add `--no-per-grower` for the combined map only.

Install or refresh the runtime copy after changing the script:

```bash
cd my-farm-advisor/data-pipeline
./scripts/install.sh --non-interactive --force-refresh
```

## Local validation

- `./scripts/validate.sh` from the repository root.
- Confirm the HTML contains the ESRI World Imagery tile URL, that the embedded
  fields are GeoJSON `Feature` objects, and that the manifest field count matches
  the grower's field inventory.
- Open the combined map in a browser for a visual check; basemap tiles require
  internet.
