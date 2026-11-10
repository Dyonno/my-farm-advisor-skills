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
- The HTML may reference online basemap tiles (ESRI World Imagery only). The
  default map must not embed rasters, imagery, NDVI, DEM, or full data bundles.
- Sentinel NDVI must stay external in the default map: convert each GeoTIFF to a
  small clipped PNG in the map's sibling `ndvi/` folder and reference it by
  relative URL (`ndvi/<file>.png`). Never inline NDVI in the default map (no
  base64, no `data:image`, no `.tif`).
- The `*_standalone.html` variant is the one exception: it exists so a single
  downloaded file works outside the runtime tree, and inlines NDVI PNGs as
  `data:image/png;base64` URIs. Keep it a separate file; never make the default
  map embedded. `--no-standalone` must skip it.
- NDVI conversion rules: clip to the field polygon, reproject EPSG:4326 to
  EPSG:3857, cap the longest side at `--ndvi-max-size` (default 512), colourise
  with the RdYlGn ramp from −0.2 to 1.0 in 64 classes, and set alpha 0 outside
  the field and for nodata.
- NDVI UI rules: one date dropdown per field (default latest scene, field's own
  scene list only), independent per-field on/off checkbox, one global opacity
  slider for all overlays, and a legend visible only while an overlay is shown.
  Keep NDVI in a pane below the field polygons so clicks and popups still work,
  and surface image load errors with the failing URL.
- Keep the embedded payload to boundary coordinates only; round coordinates to
  six decimal places and simplify only when the operator passes
  `--simplify-tolerance`. NDVI contributes URL, bounds, date, and min/max
  metadata only (plus embedded PNG bytes in the standalone variant).
- Write only under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/`: the combined map
  and its `maps/ndvi/` assets, the combined manifest in `manifests/`, and
  per-grower outputs under `growers/<grower>/` with their own `maps/ndvi/`.
  Never write generated maps or PNGs into the skill checkout or commit them.
- Keep output deterministic: sort growers, farms, fields, dates, and NDVI layers,
  use stable colors by index, and keep timestamps out of the HTML (the manifest
  may carry `generated_at`). Re-rendering with unchanged inputs must produce
  byte-identical HTML and PNGs, including the standalone variant.

## Command runbook

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/render_grower_web_map.py --grower-slug <grower-slug>
```

Omitting `--grower-slug` renders every grower into the combined map plus one map
per grower. Add `--no-per-grower` for the combined map only, `--no-ndvi` to skip
Sentinel NDVI overlays, `--ndvi-year <year>` to choose a scene year other than
2021, and `--no-standalone` to skip the single-file `*_standalone.html` copies.

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
- Confirm the default HTML contains no `data:image` or `.tif` references, and
  that each PNG in the sibling `ndvi/` folder is RGBA with transparent pixels and
  a longest side no greater than `--ndvi-max-size`.
- Confirm each `*_standalone.html` contains `data:image/png;base64` and no
  external `ndvi/` URLs, and that it opens with NDVI intact when downloaded
  alone.
- Open the combined map in a browser for a visual check; basemap tiles require
  internet. Tick NDVI for two fields on different dates and confirm both draw,
  the legend appears, and the opacity slider moves them together.
