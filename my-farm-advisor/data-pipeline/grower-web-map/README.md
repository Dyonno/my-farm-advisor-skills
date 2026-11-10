# Grower Web Map

A browser-based field map built from the polygons the data pipeline already
downloaded. It writes **one combined map covering every selected grower** plus a
small map per grower. Open the HTML directly or serve it from any static file
server.

## What it shows

- Every field for every selected grower, drawn from the pipeline's
  `field_boundaries.geojson`.
- ESRI World Imagery satellite basemap, the only background layer.
- Zoom, pan, and scale controls.
- One toggleable overlay per grower, so growers can be shown or hidden
  independently (combined map only).
- A sidebar grouped by grower and farm. Clicking a grower fits that grower's
  fields; clicking a field zooms to it and opens its popup. A **Fit all fields**
  button restores the full extent.
- Click a field for a popup with grower, farm, field name, crop, area, county,
  state, and field ID.
- Automatic fit to every field on load.

## What it deliberately does not do

- No raster, NDVI, DEM, soil, or imagery payloads embedded in the HTML.
- No data bundles or tile caches in the repository.
- No writes outside the runtime data root.
- No re-fetching of field boundaries: the pipeline's polygons are the only
  geometry source.

The HTML embeds only the boundary GeoJSON (coordinates rounded to six decimal
places) plus Leaflet bootstrapping. Expect well under 150 KB per map; the two
demo growers together are about 38 KB.

## Inputs

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/
├── growers/<grower>/grower.json
├── growers/<grower>/farms/<farm>/farm.json
└── growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson
```

The scripts use `scripts/lib/paths.py`, so `DATA_PIPELINE_DATA_ROOT` must be set
to an absolute writable path outside the skill checkout.

## Outputs

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/
├── maps/all-growers_fields_map.html
├── manifests/all_growers_web_map.json
├── growers/<grower>/maps/<grower>_fields_map.html
└── growers/<grower>/manifests/grower_web_map.json
```

The combined map is written whenever more than one grower is selected. Each
manifest records the field count, grower/farm breakdown, output size, basemap
URL, simplification tolerance, and a sha256 for every boundary file used.

## Run

From the runtime source copy after the installer has synced it:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/render_grower_web_map.py \
  --grower-slug il-demo-grower \
  --grower-slug ia-demo-grower
```

With no `--grower-slug`, every grower with a `farms/` directory is rendered into
both the combined map and its own map.

Optional flags:

- `--output-dir <abs path>` — write HTML somewhere other than the runtime maps
  folders (combined map as `<dir>/all-growers_fields_map.html`, per-grower maps
  as `<dir>/<grower>_fields_map.html`). Manifests stay in the runtime.
- `--simplify-tolerance <degrees>` — shapely simplify tolerance; `0` keeps the
  exact pipeline polygons (default).
- `--title <text>` — title shown in the combined map header and manifest.
- `--no-combined` — skip the combined all-growers map.
- `--no-per-grower` — write only the combined map.

## Verify

```bash
grep -c "World_Imagery" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/maps/all-growers_fields_map.html"
cat "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/manifests/all_growers_web_map.json"
```

Then open the combined map in a browser. The sidebar should list every grower and
field; clicking a field should zoom to it and show the popup, and the ESRI
basemap tiles should appear in the background (internet required).
