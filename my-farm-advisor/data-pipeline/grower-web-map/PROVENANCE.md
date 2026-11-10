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
- Mapping library: Leaflet 1.9.4, loaded by the browser from unpkg (BSD-2-Clause).
- Basemap tiles: ESRI World Imagery, loaded by the browser. It is the only
  background layer. The HTML embeds no tiles and caches none.
- No imagery, rasters, or provider data are redistributed by this subskill.

## Ownership

- Author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
- License: Apache-2.0 (repository default)

## Runtime outputs

Generated maps and manifests stay under the runtime data root and out of Git.
See [README.md](README.md) for the exact paths.
