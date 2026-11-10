---
name: grower-web-map
description: >
  Grower-level interactive field map for My Farm Advisor. Use when a grower or
  instructor needs a lightweight browser map of every field, on a satellite
  basemap, with zoom, click metadata, a field list, and optional per-field
  Sentinel NDVI date overlays. Consumes the field polygons and NDVI products
  already produced by the data pipeline; never embeds rasters or raw imagery.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "0.2.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "0.2.0"
---

# Grower Web Map

Use this nested subskill to turn the data pipeline's downloaded field polygons
into a small, self-contained interactive HTML map for one grower. It is a
delivery/reporting step, not an ingest step: it reads what the pipeline already
wrote and adds no new remote data beyond the basemap tiles loaded by the browser.

## Start Here

- Read [README.md](README.md) for inputs, outputs, commands, and the size budget.
- Read [AGENTS.md](AGENTS.md) for local operating rules and edit scope.
- Read [PROVENANCE.md](PROVENANCE.md) for the source and ownership record.
- Open [`../src/scripts/render_grower_web_map.py`](../src/scripts/render_grower_web_map.py)
  for the implementation and CLI flags.

## Runtime Contract

- Input: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson`
- NDVI input: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/fields/<field>/satellite/sentinel/<year>/*/sentinel_<YYYYMMDD>_ndvi.tif`
- Combined map: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/maps/all-growers_fields_map.html`
- Combined standalone map: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/maps/all-growers_fields_map_standalone.html`
- NDVI overlays (combined): `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/maps/ndvi/<grower>__<farm>__<field>__sentinel_<YYYYMMDD>.png`
- NDVI overlays (per grower): `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/maps/ndvi/<grower>__<farm>__<field>__sentinel_<YYYYMMDD>.png`
- Combined manifest: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/manifests/all_growers_web_map.json`
- Per-grower map: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/maps/<grower>_fields_map.html`
- Per-grower standalone map: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/maps/<grower>_fields_map_standalone.html`
- Per-grower manifest: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/manifests/grower_web_map.json`
- Everything generated stays under the runtime root and out of Git.

One combined map covers every selected grower, with a toggleable overlay per
grower and a grower/farm/field sidebar. Per-grower maps are still written unless
`--no-per-grower` is passed.

Sentinel NDVI for the requested year (`--ndvi-year`, default `2021`) is written
as small clipped PNGs next to each map and referenced by relative URL. Each field
gets its own date dropdown and on/off checkbox, one global opacity slider drives
every visible overlay, and a legend appears while any overlay is shown. A
`*_standalone.html` copy embeds the PNGs as data URIs for single-file download;
`--no-ndvi` renders boundaries only and `--no-standalone` skips the embedded copy.

The implementation ships inside `data-pipeline/src/scripts/`, so the existing
runtime installer copies it into
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts/` automatically.
