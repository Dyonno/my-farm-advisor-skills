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
- Optional Sentinel NDVI overlays for every available scene of a chosen year
  (2021 by default). Each field has its own date dropdown and on/off checkbox,
  so different fields can show different dates at the same time. One global
  opacity slider controls all overlays, and a legend appears while any overlay is
  visible. See [Sentinel NDVI overlays](#sentinel-ndvi-overlays).

## What it deliberately does not do

- No raster, NDVI, DEM, soil, or imagery payloads embedded in the **default**
  HTML. NDVI is written as small external PNGs and referenced by relative URL.
  A separate `*_standalone.html` variant embeds those PNGs for single-file
  download when you need to move one file outside the runtime tree (see
  [Single-file download](#single-file-download)).
- No data bundles or tile caches in the repository.
- No writes outside the runtime data root.
- No re-fetching of field boundaries: the pipeline's polygons are the only
  geometry source.
- No NDVI reprocessing: the pipeline's Sentinel NDVI GeoTIFFs are the only
  vegetation source; this step only clips, reprojects, colourises, and caches
  them as PNG overlays.

The default HTML embeds only the boundary GeoJSON (coordinates rounded to six
decimal places), NDVI layer metadata, and Leaflet bootstrapping. Expect well
under 150 KB per map; the two demo growers together are about 59 KB including 43
NDVI layer records, while the 43 PNG overlays total about 620 KB. The optional
combined standalone file is about 880 KB.

## Inputs

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/
├── growers/<grower>/grower.json
├── growers/<grower>/farms/<farm>/farm.json
├── growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson
└── growers/<grower>/farms/<farm>/fields/<field>/satellite/sentinel/<year>/
    └── sentinel_<YYYYMMDD>/sentinel_<YYYYMMDD>_ndvi.tif
```

The scripts use `scripts/lib/paths.py`, so `DATA_PIPELINE_DATA_ROOT` must be set
to an absolute writable path outside the skill checkout. NDVI overlays are
skipped automatically when no matching Sentinel NDVI GeoTIFFs exist.

## Outputs

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/
├── maps/all-growers_fields_map.html
├── maps/all-growers_fields_map_standalone.html          # embedded NDVI
├── maps/ndvi/<grower>__<farm>__<field>__sentinel_<YYYYMMDD>.png
├── manifests/all_growers_web_map.json
├── manifests/all_growers_web_map_standalone.json
├── growers/<grower>/maps/<grower>_fields_map.html
├── growers/<grower>/maps/<grower>_fields_map_standalone.html
├── growers/<grower>/maps/ndvi/<grower>__<farm>__<field>__sentinel_<YYYYMMDD>.png
└── growers/<grower>/manifests/grower_web_map.json
```

The combined map is written whenever more than one grower is selected. Each
manifest records the field count, grower/farm breakdown, output size, basemap
URL, simplification tolerance, and a sha256 for every boundary file used. When
NDVI is included, the manifest also records the year, sensor, colour-ramp
range, whether the file is embedded (`standalone`), the available dates, and
every PNG's path, size, and sha256.

The `*_standalone.html` (and its manifest) is written only when NDVI is present;
use `--no-standalone` to skip it.

## Sentinel NDVI overlays

Each 2021 Sentinel NDVI GeoTIFF is converted once per run into a small
transparent PNG:

- clipped to the field's `field_boundary.geojson`, so NDVI stops at the field
  edge even where the source raster bleeds outside it;
- reprojected from EPSG:4326 to web mercator (EPSG:3857) so it aligns with the
  Leaflet tiles;
- resampled to at most 512 px on the longest side (`--ndvi-max-size`);
- colourised with the matplotlib **RdYlGn** ramp from −0.2 to 1.0 in 64 classes,
  with alpha 0 everywhere outside the field or where the raster is nodata;
- written as 8-bit RGBA PNG.

PNGs are written **next to each map** in a sibling `ndvi/` folder and referenced
with a relative URL, so any map keeps working after being copied together with
its `ndvi/` folder:

- combined map → `maps/ndvi/`
- per-grower map → `growers/<grower>/maps/ndvi/`
- with `--output-dir <dir>` → both use `<dir>/ndvi/`

The renderer deduplicates: re-running rewrites identical bytes, and the same
scene is reused across runs.

Map behaviour:

- A **Sentinel NDVI · 2021** panel appears when at least one field has data.
- Every field row with NDVI gets a checkbox and a date dropdown listing only that
  field's available scenes. The dropdown defaults to the field's latest scene;
  the checkbox starts unchecked.
- Changing one field's date swaps only that field's overlay. Other fields keep
  their own dates, so e.g. one field can show August while another shows June.
- The **Opacity** slider (0–100%, default 100%) changes every visible overlay at
  once.
- The RdYlGn legend appears bottom-right as soon as any overlay is visible and
  hides when none are.
- NDVI renders in its own pane below the field polygons, so boundaries, popups,
  and clicks keep working; field fill opacity drops to 0.06 so NDVI colours read
  true.
- If an NDVI image cannot be loaded, the sidebar shows the failed URL instead of
  a silent broken-image icon.

## Single-file download

Downloading just the default HTML fails to show NDVI unless the sibling `ndvi/`
folder comes too. Each map is therefore also written as a single-file copy that
inlines the PNGs as base64 `data:` URIs:

```text
maps/all-growers_fields_map_standalone.html
growers/<grower>/maps/<grower>_fields_map_standalone.html
```

Download that file and open it directly in a browser; no companion assets are
needed (the ESRI basemap still needs internet). The default maps stay small for
serving, and the `_standalone` files exist for portability. Pass
`--no-standalone` to skip generating them.

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
- `--ndvi-year <year>` — Sentinel NDVI scene year to render as overlays
  (default `2021`).
- `--ndvi-max-size <px>` — maximum overlay image dimension (default `512`).
  Smaller values make lighter PNGs; larger values show more detail.
- `--no-ndvi` — skip NDVI overlays and render boundaries only.
- `--no-standalone` — skip the single-file `*_standalone.html` variants.
- `--no-combined` — skip the combined all-growers map.
- `--no-per-grower` — write only the combined map.

NDVI is included automatically when the requested year has Sentinel NDVI
GeoTIFFs under the field tree; no extra flag is needed.

## Verify

```bash
grep -c "World_Imagery" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/maps/all-growers_fields_map.html"
grep -c "data:image" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/maps/all-growers_fields_map.html"  # expect 0
grep -c "data:image/png;base64" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/maps/all-growers_fields_map_standalone.html"  # > 0
find "${DATA_PIPELINE_DATA_ROOT}/data-pipeline" -path '*/ndvi/*.png' | wc -l
cat "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/manifests/all_growers_web_map.json"
```

Then open the combined map in a browser. The sidebar should list every grower and
field; clicking a field should zoom to it and show the popup, and the ESRI
basemap tiles should appear in the background (internet required). Tick **NDVI**
on two fields with different dates: both overlays should draw, the legend should
appear, and the opacity slider should fade them together.

To check the portable single file, download only
`maps/all-growers_fields_map_standalone.html` to any folder and open it. NDVI
should display without any `ndvi/` folder beside it.
