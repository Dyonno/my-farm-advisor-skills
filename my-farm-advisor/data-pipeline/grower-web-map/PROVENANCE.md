# Provenance

## Origin

This subskill was authored for the My Farm Advisor skill catalog on the
`assignment-1` branch. It is an original implementation; no third-party skill
code was imported or copied.

## Inputs and dependencies

- Field polygons: produced by the My Farm Advisor data pipeline
  (`data-pipeline/src/scripts/ingest/download_csb_fields.py` and
  `download_fields.py`) and stored under
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/`.
- Grower and farm metadata: pipeline-written `grower.json` and `farm.json`.
- Sentinel NDVI: Sentinel-2 L2A scenes downloaded, cloud-masked, and reduced to
  NDVI GeoTIFFs by the My Farm Advisor data pipeline (Satellite/NDVI step) and
  stored under each field's `satellite/sentinel/<year>/` directory. This subskill
  only clips, reprojects (`EPSG:4326` → `EPSG:3857`), colourises (matplotlib
  RdYlGn, −0.2 to 1.0), and caches them as PNG overlays; it does not re-fetch or
  re-derive NDVI. Sentinel data is Copernicus Sentinel data (ESA), subject to the
  Copernicus data policy; no source rasters are redistributed here. Each chosen
  scene is converted to a small clipped PNG; the `*_standalone.html` variant
  embeds those derived PNGs as base64 so a single file can be shared.
- Mapping library: Leaflet 1.9.4, loaded by the browser from unpkg (BSD-2-Clause).
- Colour ramp: matplotlib `RdYlGn` (matplotlib licence, BSD-style).
- Basemap tiles: ESRI World Imagery, loaded by the browser. It is the only
  background layer. The HTML embeds no tiles and caches none.
- No imagery, rasters, or provider data are redistributed by this subskill.

## Ownership

- Author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
- License: Apache-2.0 (repository default)

## Runtime outputs

Generated maps, standalone (embedded) maps, NDVI PNG overlays, and manifests stay
under the runtime data root and out of Git. See [README.md](README.md) for the
exact paths.
