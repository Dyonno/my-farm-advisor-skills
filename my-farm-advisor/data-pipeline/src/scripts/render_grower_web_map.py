#!/usr/bin/env python3
"""Render lightweight interactive field maps from pipeline field boundaries.

Reads the field polygons produced by the data pipeline and writes self-contained
HTML maps that use Leaflet + ESRI World Imagery tiles. Two shapes are produced:

  * one combined map covering every selected grower, and
  * one map per grower.

Optionally, Sentinel NDVI scenes for a chosen year are converted to small,
field-clipped, transparent PNG overlays that can be shown per field and per
date. NDVI images are written next to each map and referenced by URL, so the
HTML stays small. A ``*_standalone.html`` copy embeds those PNGs as data URIs
for downloading a single file; rasters and basemap imagery are never embedded.

Outputs (under the runtime data root, never in the skill checkout):
  maps/all-growers_fields_map.html
  maps/ndvi/<grower>__<farm>__<field>__sentinel_<YYYYMMDD>.png
  manifests/all_growers_web_map.json
  growers/<grower>/maps/<grower>_fields_map.html
  growers/<grower>/maps/ndvi/<grower>__<farm>__<field>__sentinel_<YYYYMMDD>.png
  growers/<grower>/manifests/grower_web_map.json
  plus *_standalone.html (and *_standalone.json) when NDVI is present.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import html
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.paths import (  # noqa: E402
    DATA_ROOT,
    GROWERS_ROOT,
    farm_boundary_path,
    field_satellite_dir,
    grower_dir,
)

ESRI_WORLD_IMAGERY = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
ESRI_ATTRIBUTION = (
    "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, "
    "and the GIS User Community"
)

PALETTE = (
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
    "#f032e6", "#bfef45", "#fabed4", "#469990", "#dcbeff", "#9a6324",
)

NDVI_SENSOR = "sentinel"
NDVI_VMIN = -0.2
NDVI_VMAX = 1.0
NDVI_MAX_SIZE = 512
NDVI_CLASSES = 64
NDVI_RAMP_NAME = "RdYlGn"
_NDVI_FALLBACK_HEXES = (
    "#a50026", "#d73027", "#f46d43", "#fdae61", "#fee08b", "#ffffbf",
    "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850", "#006837",
)
_NDVI_TICK_LABELS = ("−0.2", "0", "0.2", "0.4", "0.6", "0.8", "1.0")

STATE_TOKENS = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
}


def _slug_label(slug: str) -> str:
    tokens = []
    for token in slug.split("-"):
        if not token:
            continue
        tokens.append(token.upper() if token.lower() in STATE_TOKENS else token.capitalize())
    return " ".join(tokens) or slug


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _grower_name(grower_slug: str) -> str:
    meta = _read_json(grower_dir(grower_slug) / "grower.json")
    display = str(meta.get("display_name") or "").strip()
    if display and display != grower_slug:
        return display
    return _slug_label(grower_slug)


def _farm_name(grower_slug: str, farm_slug: str) -> str:
    meta = _read_json(grower_dir(grower_slug) / "farms" / farm_slug / "farm.json")
    display = str(meta.get("display_name") or "").strip()
    return display or _slug_label(farm_slug)


def _round_coords(value: Any, digits: int = 6) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), digits)
    if isinstance(value, list):
        return [_round_coords(item, digits) for item in value]
    if isinstance(value, dict):
        return {key: _round_coords(item, digits) for key, item in value.items()}
    return value


def _iter_points(coords: Any):
    if (
        isinstance(coords, list)
        and len(coords) == 2
        and all(isinstance(part, (int, float)) for part in coords)
    ):
        yield float(coords[0]), float(coords[1])
        return
    if isinstance(coords, list):
        for item in coords:
            yield from _iter_points(item)


def _simplify_geometry(geometry: dict[str, Any], tolerance: float) -> dict[str, Any]:
    if tolerance <= 0:
        return geometry
    try:
        from shapely.geometry import mapping, shape
    except Exception:  # pragma: no cover - optional optimization only
        return geometry
    simplified = shape(geometry).simplify(tolerance, preserve_topology=True)
    if simplified.is_empty:
        return geometry
    return dict(mapping(simplified))


def _load_farm_fields(
    grower_slug: str,
    grower_name: str,
    farm_slug: str,
    *,
    simplify_tolerance: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return GeoJSON Features for one farm plus the boundary files used."""
    boundary_path = farm_boundary_path(grower_slug, farm_slug)
    if not boundary_path.exists():
        print(f"  warn  {grower_slug}/{farm_slug}: boundary missing ({boundary_path})")
        return [], []

    payload = _read_json(boundary_path)
    features = payload.get("features")
    if not isinstance(features, list):
        print(f"  warn  {grower_slug}/{farm_slug}: no features in {boundary_path.name}")
        return [], []

    farm_name = _farm_name(grower_slug, farm_slug)
    rows: list[dict[str, Any]] = []

    for feature in features:
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or not geometry.get("coordinates"):
            continue
        props = feature.get("properties") or {}
        field_id = str(props.get("field_id") or "").strip()
        if not field_id:
            continue
        rows.append(
            {
                "raw_props": props,
                "geometry": _simplify_geometry(geometry, simplify_tolerance),
                "field_id": field_id,
            }
        )

    rows.sort(key=lambda row: row["field_id"])
    features_out: list[dict[str, Any]] = []
    for row in rows:
        props = row["raw_props"]
        features_out.append(
            {
                "type": "Feature",
                "geometry": _round_coords(row["geometry"]),
                "properties": {
                    "id": row["field_id"],
                    "name": str(props.get("name") or props.get("field_name") or row["field_id"]),
                    "grower_slug": grower_slug,
                    "grower_name": grower_name,
                    "farm_slug": farm_slug,
                    "farm_name": farm_name,
                    "crop": str(props.get("crop") or "—"),
                    "acres": props.get("area_acres"),
                    "hectares": props.get("area_ha_est"),
                    "county": str(props.get("county") or "—"),
                    "state": str(props.get("state") or "—"),
                    "color": None,
                },
            }
        )
    sources = [str(boundary_path)] * len(features_out)
    return features_out, sources


def _bounds(features: list[dict[str, Any]]) -> list[list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        for lon, lat in _iter_points(geometry.get("coordinates")):
            xs.append(lon)
            ys.append(lat)
    if not xs:
        return []
    return [[min(ys), min(xs)], [max(ys), max(xs)]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(DATA_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _ndvi_scene_paths(
    grower_slug: str,
    farm_slug: str,
    field_slug: str,
    year: int,
) -> list[tuple[str, Path]]:
    """Return (ISO date, ndvi tif) for every scene of a field and year."""
    sensor_dir = field_satellite_dir(grower_slug, farm_slug, field_slug) / NDVI_SENSOR / str(year)
    if not sensor_dir.exists():
        return []
    pattern = re.compile(rf"^{NDVI_SENSOR}_(\d{{8}})_ndvi\.tif$")
    scenes: list[tuple[str, Path]] = []
    for tif in sorted(sensor_dir.rglob(f"{NDVI_SENSOR}_*_ndvi.tif")):
        match = pattern.match(tif.name)
        if not match:
            continue
        stamp = match.group(1)
        scenes.append((f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}", tif))
    scenes.sort(key=lambda item: item[0])
    return scenes


def _render_ndvi(
    tif_path: Path,
    geometry: dict[str, Any],
    *,
    max_size: int,
) -> dict[str, Any] | None:
    """Clip an NDVI raster to a field, warp to web mercator, and encode a PNG."""
    try:
        import io

        import numpy as np
        import rasterio
        from matplotlib import colormaps
        from pyproj import Transformer
        from rasterio.features import geometry_mask
        from rasterio.transform import Affine, array_bounds
        from rasterio.warp import Resampling, calculate_default_transform, reproject
        from PIL import Image
    except Exception as exc:  # pragma: no cover - dependency guard
        raise SystemExit(
            "NDVI overlays need rasterio, pyproj, numpy, Pillow, and matplotlib "
            f"in the runtime virtualenv ({exc}). Re-run with --no-ndvi to skip."
        )

    try:
        with rasterio.open(tif_path) as src:
            values = src.read(1, masked=True).astype("float64").filled(np.nan)
            if values.size == 0 or not np.isfinite(values).any():
                return None
            inside = geometry_mask(
                [geometry], out_shape=values.shape, transform=src.transform, invert=True
            )
            valid = np.isfinite(values) & inside
            if not valid.any():
                return None
            values = np.where(valid, values, np.nan)
            src_transform = src.transform
            src_crs = src.crs
            src_bounds = src.bounds
            src_width, src_height = src.width, src.height
            dst_transform, dst_w, dst_h = calculate_default_transform(
                src_crs, "EPSG:3857", src_width, src_height, *src_bounds
            )
    except Exception as exc:
        print(f"  warn  NDVI raster unreadable ({tif_path.name}): {exc}")
        return None

    if max(dst_w, dst_h) > max_size:
        scale = max_size / max(dst_w, dst_h)
        new_w = max(1, int(round(dst_w * scale)))
        new_h = max(1, int(round(dst_h * scale)))
        dst_transform = dst_transform * Affine.scale(dst_w / new_w, dst_h / new_h)
        dst_w, dst_h = new_w, new_h

    warped = np.full((dst_h, dst_w), np.nan, dtype="float32")
    reproject(
        source=values,
        destination=warped,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=np.nan,
        dst_transform=dst_transform,
        dst_crs="EPSG:3857",
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )

    valid = np.isfinite(warped)
    if not valid.any():
        return None

    normalised = np.clip((warped - NDVI_VMIN) / (NDVI_VMAX - NDVI_VMIN), 0.0, 1.0)
    normalised = np.nan_to_num(normalised, nan=0.0)
    normalised = np.round(normalised * (NDVI_CLASSES - 1)) / (NDVI_CLASSES - 1)
    cmap = colormaps[NDVI_RAMP_NAME]
    rgba = (cmap(normalised) * 255).astype("uint8")
    rgba[..., 3] = np.where(valid, 255, 0).astype("uint8")

    buffer = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG", optimize=True)

    left, bottom, right, top = array_bounds(dst_h, dst_w, dst_transform)
    to_wgs84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    west, south = to_wgs84.transform(left, bottom)
    east, north = to_wgs84.transform(right, top)
    stats = warped[valid]
    return {
        "png": buffer.getvalue(),
        "bounds": [[south, west], [north, east]],
        "min": round(float(stats.min()), 4),
        "max": round(float(stats.max()), 4),
        "width": dst_w,
        "height": dst_h,
    }


def _collect_ndvi(
    features: list[dict[str, Any]],
    *,
    year: int,
    asset_dir: Path,
    cache: dict[Any, Any],
    max_size: int,
) -> dict[str, Any] | None:
    layers: list[dict[str, Any]] = []
    asset_dir.mkdir(parents=True, exist_ok=True)
    for feature in features:
        props = feature["properties"]
        field_key = f"{props['grower_slug']}::{props['id']}"
        for date, tif in _ndvi_scene_paths(
            props["grower_slug"], props["farm_slug"], props["id"], year
        ):
            cache_key = (props["grower_slug"], props["farm_slug"], props["id"], date)
            if cache_key not in cache:
                cache[cache_key] = _render_ndvi(
                    tif, feature["geometry"], max_size=max_size
                )
            entry = cache[cache_key]
            if not entry:
                continue
            png_path = asset_dir / (
                f"{props['grower_slug']}__{props['farm_slug']}__{props['id']}"
                f"__{NDVI_SENSOR}_{date.replace('-', '')}.png"
            )
            if not png_path.exists() or png_path.read_bytes() != entry["png"]:
                png_path.write_bytes(entry["png"])
            layers.append(
                {
                    "field_key": field_key,
                    "grower_slug": props["grower_slug"],
                    "farm_slug": props["farm_slug"],
                    "field_id": props["id"],
                    "date": date,
                    "image": str(png_path),
                    "bounds": entry["bounds"],
                    "min": entry["min"],
                    "max": entry["max"],
                    "width": entry["width"],
                    "height": entry["height"],
                }
            )

    if not layers:
        return None

    layers.sort(key=lambda layer: (layer["field_key"], layer["date"]))
    return {
        "year": year,
        "sensor": NDVI_SENSOR,
        "vmin": NDVI_VMIN,
        "vmax": NDVI_VMAX,
        "dates": sorted({layer["date"] for layer in layers}),
        "layers": layers,
    }


def _ndvi_legend() -> tuple[str, str]:
    stops = [index / 10 for index in range(11)]
    try:
        from matplotlib import colormaps, colors

        cmap = colormaps[NDVI_RAMP_NAME]
        hexes = [colors.to_hex(cmap(stop)) for stop in stops]
    except Exception:  # pragma: no cover - fallback only
        hexes = list(_NDVI_FALLBACK_HEXES)
    gradient = "linear-gradient(to right, " + ", ".join(
        f"{colour} {round(stop * 100)}%" for stop, colour in zip(stops, hexes)
    ) + ")"
    ticks = "".join(f"<span>{label}</span>" for label in _NDVI_TICK_LABELS)
    return gradient, ticks


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
  :root { --panel: #ffffff; --ink: #1f2933; --muted: #6b7280; --line: #d7dde5; }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--ink); }
  #app { display: flex; height: 100%; }
  #sidebar { width: 340px; min-width: 270px; max-width: 42%; background: var(--panel);
             border-right: 1px solid var(--line); display: flex; flex-direction: column; }
  #sidebar header { padding: 14px 16px 12px; border-bottom: 1px solid var(--line); }
  #sidebar h1 { font-size: 1rem; margin: 0 0 2px; }
  #sidebar p { margin: 0; color: var(--muted); font-size: 0.78rem; }
  #fit-all { margin-top: 10px; width: 100%; padding: 7px 10px; border-radius: 8px;
             border: 1px solid var(--line); background: #f7f9fc; font: inherit;
             font-size: 0.82rem; cursor: pointer; }
  #fit-all:hover, #fit-all:focus-visible { background: #eef3fa; }
  .error { margin: 10px; padding: 8px 10px; border-radius: 8px;
           background: #fdecec; color: #b42318; font-size: 0.78rem; }
  .ndvi-panel { padding: 10px 16px 12px; border-bottom: 1px solid var(--line); }
  .ndvi-panel h2 { font-size: 0.7rem; text-transform: uppercase; letter-spacing: .06em;
                   color: var(--muted); margin: 0 0 8px; }
  .opacity-row { display: flex; align-items: center; gap: 8px; font-size: 0.78rem; }
  .opacity-row input[type=range] { flex: 1; min-width: 0; }
  .opacity-row .value { color: var(--muted); width: 38px; text-align: right; }
  .ndvi-panel .hint { margin: 6px 0 0; color: var(--muted); font-size: 0.72rem; }
  #field-list { overflow-y: auto; padding: 8px 10px 20px; }
  #field-list section + section { margin-top: 14px; }
  #field-list h2 { font-size: 0.7rem; text-transform: uppercase; letter-spacing: .06em;
                   color: var(--muted); margin: 12px 8px 4px; }
  .grower-item { display: flex; flex-direction: column; gap: 2px; width: 100%; text-align: left;
                 border: 1px solid var(--line); background: #f7f9fc; padding: 9px 10px;
                 border-radius: 8px; cursor: pointer; font: inherit; }
  .grower-item:hover, .grower-item:focus-visible { background: #eef3fa; }
  .grower-item .label { font-weight: 600; font-size: 0.9rem; }
  .grower-item .meta { color: var(--muted); font-size: 0.72rem; }
  .field-row { border-bottom: 1px solid #eef1f5; }
  .field-row:last-child { border-bottom: 0; }
  .field-item { display: flex; align-items: center; gap: 8px; width: 100%; text-align: left;
                border: 1px solid transparent; background: none; padding: 7px 8px;
                border-radius: 8px; cursor: pointer; font: inherit; }
  .field-item:hover, .field-item:focus-visible { background: #f2f6fb; border-color: var(--line); }
  .field-item .label { display: block; font-size: 0.85rem; }
  .field-item .meta { display: block; color: var(--muted); font-size: 0.72rem; }
  .swatch { width: 12px; height: 12px; border-radius: 3px; flex: none; }
  .ndvi-controls { display: flex; align-items: center; gap: 8px; padding: 0 8px 8px 28px; }
  .ndvi-toggle { display: flex; align-items: center; gap: 4px; font-size: 0.74rem;
                 color: var(--muted); cursor: pointer; }
  .ndvi-date { flex: 1; min-width: 0; font: inherit; font-size: 0.74rem; padding: 2px 4px;
               border: 1px solid var(--line); border-radius: 6px; background: #fff; color: var(--ink); }
  #map-wrap { position: relative; flex: 1; min-width: 0; }
  #map { width: 100%; height: 100%; }
  .ndvi-legend { position: absolute; right: 14px; bottom: 30px; z-index: 600; width: 190px;
                 background: rgba(255, 255, 255, 0.95); border: 1px solid var(--line);
                 border-radius: 8px; padding: 8px 10px 6px; font-size: 0.7rem; }
  .ndvi-legend .caption { font-weight: 600; font-size: 0.68rem; margin-bottom: 4px; }
  .ndvi-legend .bar { height: 10px; border-radius: 3px; }
  .ndvi-legend .ticks { display: flex; justify-content: space-between; color: var(--muted);
                        font-size: 0.62rem; margin-top: 2px; }
  .popup table { border-collapse: collapse; font-size: 0.82rem; }
  .popup th { text-align: left; color: var(--muted); font-weight: 500; padding: 1px 10px 1px 0; white-space: nowrap; }
  .popup td { padding: 1px 0; }
  .popup h3 { margin: 0 0 6px; font-size: 0.95rem; }
  @media (max-width: 720px) {
    #app { flex-direction: column; }
    #sidebar { width: 100%; max-width: none; max-height: 46%; border-right: 0; border-bottom: 1px solid var(--line); }
  }
</style>
</head>
<body>
<div id="app">
  <aside id="sidebar">
    <header>
      <h1 id="map-title"></h1>
      <p id="map-summary"></p>
      <button id="fit-all" type="button">Fit all fields</button>
    </header>
    <section id="ndvi-panel" class="ndvi-panel" hidden>
      <h2>Sentinel NDVI · <span id="ndvi-year"></span></h2>
      <div class="opacity-row">
        <label for="ndvi-opacity">Opacity</label>
        <input id="ndvi-opacity" type="range" min="0" max="100" step="1" value="100" />
        <span id="ndvi-opacity-value" class="value">100%</span>
      </div>
      <p class="hint">Pick a date per field, then tick NDVI to display it.</p>
    </section>
    <div id="error" class="error" hidden></div>
    <nav id="field-list" aria-label="Fields"></nav>
  </aside>
  <div id="map-wrap">
    <div id="map" role="application" aria-label="Field map"></div>
    <div id="ndvi-legend" class="ndvi-legend" hidden>
      <div class="caption">Sentinel NDVI · <span id="ndvi-legend-year"></span></div>
      <div class="bar" style="background: __NDVI_GRADIENT__;"></div>
      <div class="ticks">__NDVI_TICKS__</div>
    </div>
  </div>
</div>
<script>
  const MAP_DATA = __MAP_DATA__;
  const PALETTE = __PALETTE__;

  function showError(message) {
    const banner = document.getElementById("error");
    if (!banner) return;
    banner.hidden = false;
    banner.textContent = message;
  }

  function showFatal(message) {
    showError("Map failed to initialise: " + message);
  }

  function popupContent(props) {
    const wrap = document.createElement("div");
    wrap.className = "popup";
    const title = document.createElement("h3");
    title.textContent = props.name;
    wrap.appendChild(title);
    const table = document.createElement("table");
    const rows = [
      ["Grower", props.grower_name],
      ["Farm", props.farm_name],
      ["Field", props.name],
      ["Crop", props.crop],
      ["Area", props.acres != null ? props.acres + " ac" +
        (props.hectares != null ? " (" + props.hectares + " ha)" : "") : "—"],
      ["County", props.county],
      ["State", props.state],
      ["Field ID", props.id]
    ];
    for (const [label, value] of rows) {
      const tr = document.createElement("tr");
      const th = document.createElement("th");
      th.textContent = label;
      const td = document.createElement("td");
      td.textContent = String(value);
      tr.append(th, td);
      table.appendChild(tr);
    }
    wrap.appendChild(table);
    return wrap;
  }

  function init() {
    const map = L.map("map", { zoomControl: true, preferCanvas: true, minZoom: 3 });
    map.setView([42.2, -93.6], 5);
    map.createPane("ndvi");
    map.getPane("ndvi").style.zIndex = 350;

    const esri = L.tileLayer("__ESRI__", {
      maxZoom: 19,
      attribution: "__ESRI_ATTRIBUTION__"
    });
    esri.addTo(map);

    const layersById = new Map();
    const growerLayers = new Map();
    const overlays = {};

    for (const grower of MAP_DATA.growers) {
      const features = MAP_DATA.features.filter(
        (feature) => feature.properties.grower_slug === grower.slug
      );
      if (!features.length) continue;
      const layer = L.geoJSON({ type: "FeatureCollection", features: features }, {
        style: (feature) => ({
          color: feature.properties.color,
          weight: 2,
          opacity: 0.95,
          fillColor: feature.properties.color,
          fillOpacity: 0.06
        }),
        onEachFeature: (feature, fieldLayer) => {
          const props = feature.properties;
          layersById.set(props.grower_slug + "::" + props.id, fieldLayer);
          fieldLayer.bindPopup(() => popupContent(props));
          fieldLayer.on("mouseover", () => fieldLayer.setStyle({ fillOpacity: 0.18 }));
          fieldLayer.on("mouseout", () => fieldLayer.setStyle({ fillOpacity: 0.06 }));
        }
      });
      layer.addTo(map);
      growerLayers.set(grower.slug, layer);
      overlays[grower.name] = layer;
    }

    if (Object.keys(overlays).length > 1) {
      L.control.layers(null, overlays, { collapsed: false }).addTo(map);
    }
    L.control.scale({ imperial: true, metric: true }).addTo(map);

    const farmCount = MAP_DATA.growers.reduce((total, grower) => total + grower.farm_count, 0);
    document.getElementById("map-title").textContent = MAP_DATA.title;
    document.getElementById("map-summary").textContent =
      MAP_DATA.features.length + " fields · " + MAP_DATA.growers.length +
      (MAP_DATA.growers.length === 1 ? " grower · " : " growers · ") + farmCount +
      (farmCount === 1 ? " farm" : " farms");

    // ---- NDVI overlays (per field, per date) ----
    const ndvi = MAP_DATA.ndvi || null;
    const ndviLayers = new Map();      // "fieldKey|date" -> layer payload
    const ndviDates = new Map();        // fieldKey -> [dates]
    const activeOverlays = new Map();   // fieldKey -> L.imageOverlay
    if (ndvi) {
      for (const layer of ndvi.layers) {
        ndviLayers.set(layer.field_key + "|" + layer.date, layer);
        if (!ndviDates.has(layer.field_key)) ndviDates.set(layer.field_key, []);
        ndviDates.get(layer.field_key).push(layer.date);
      }
      document.getElementById("ndvi-year").textContent = ndvi.year;
      document.getElementById("ndvi-legend-year").textContent = ndvi.year;
      document.getElementById("ndvi-panel").hidden = false;
    }

    const opacitySlider = document.getElementById("ndvi-opacity");
    const opacityValue = document.getElementById("ndvi-opacity-value");
    const legend = document.getElementById("ndvi-legend");

    function currentOpacity() {
      return Number(opacitySlider.value) / 100;
    }

    function updateLegend() {
      legend.hidden = activeOverlays.size === 0;
    }

    function setFieldNdvi(fieldKey, checked, date) {
      const existing = activeOverlays.get(fieldKey);
      if (existing) {
        map.removeLayer(existing);
        activeOverlays.delete(fieldKey);
      }
      if (checked && date) {
        const layer = ndviLayers.get(fieldKey + "|" + date);
        if (layer) {
          const overlay = L.imageOverlay(layer.url, layer.bounds, {
            opacity: currentOpacity(),
            pane: "ndvi",
            interactive: false
          });
          overlay.on("error", () => {
            const source = String(layer.url).startsWith("data:")
              ? "embedded NDVI image"
              : layer.url;
            showError("NDVI image failed to load: " + source);
          });
          overlay.addTo(map);
          activeOverlays.set(fieldKey, overlay);
        }
      }
      updateLegend();
    }

    opacitySlider.addEventListener("input", () => {
      const value = Number(opacitySlider.value);
      opacityValue.textContent = value + "%";
      for (const overlay of activeOverlays.values()) overlay.setOpacity(value / 100);
    });

    const list = document.getElementById("field-list");
    for (const grower of MAP_DATA.growers) {
      if (!growerLayers.has(grower.slug)) continue;
      const section = document.createElement("section");

      const growerButton = document.createElement("button");
      growerButton.type = "button";
      growerButton.className = "grower-item";
      const growerLabel = document.createElement("span");
      growerLabel.className = "label";
      growerLabel.textContent = grower.name;
      const growerMeta = document.createElement("span");
      growerMeta.className = "meta";
      growerMeta.textContent = grower.field_count + " fields · " + grower.farm_count +
        (grower.farm_count === 1 ? " farm" : " farms") + " · click to zoom";
      growerButton.append(growerLabel, growerMeta);
      growerButton.addEventListener("click", () => {
        const layer = growerLayers.get(grower.slug);
        if (layer && layer.getBounds().isValid()) {
          map.fitBounds(layer.getBounds(), { padding: [40, 40] });
        }
      });
      section.appendChild(growerButton);

      let currentFarm = null;
      for (const feature of MAP_DATA.features) {
        const props = feature.properties;
        if (props.grower_slug !== grower.slug) continue;
        if (props.farm_slug !== currentFarm) {
          currentFarm = props.farm_slug;
          const heading = document.createElement("h2");
          heading.textContent = props.farm_name;
          section.appendChild(heading);
        }

        const row = document.createElement("div");
        row.className = "field-row";

        const button = document.createElement("button");
        button.type = "button";
        button.className = "field-item";
        const swatch = document.createElement("span");
        swatch.className = "swatch";
        swatch.style.background = props.color;
        const text = document.createElement("span");
        const label = document.createElement("span");
        label.className = "label";
        label.textContent = props.name;
        const meta = document.createElement("span");
        meta.className = "meta";
        meta.textContent = [props.crop, props.acres != null ? props.acres + " ac" : null]
          .filter(Boolean).join(" · ");
        text.append(label, meta);
        button.append(swatch, text);
        button.addEventListener("click", () => {
          const layer = layersById.get(props.grower_slug + "::" + props.id);
          if (!layer) return;
          map.fitBounds(layer.getBounds(), { padding: [40, 40], maxZoom: 16 });
          layer.openPopup();
        });
        row.appendChild(button);

        const fieldKey = props.grower_slug + "::" + props.id;
        const dates = ndviDates.get(fieldKey);
        if (dates && dates.length) {
          const controls = document.createElement("div");
          controls.className = "ndvi-controls";

          const toggle = document.createElement("label");
          toggle.className = "ndvi-toggle";
          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.className = "ndvi-check";
          const toggleText = document.createElement("span");
          toggleText.textContent = "NDVI";
          toggle.append(checkbox, toggleText);

          const select = document.createElement("select");
          select.className = "ndvi-date";
          select.setAttribute("aria-label", "NDVI date for " + props.name);
          for (const date of dates.slice().reverse()) {
            const option = document.createElement("option");
            option.value = date;
            option.textContent = date;
            select.appendChild(option);
          }
          select.value = dates[dates.length - 1];

          const refresh = () => setFieldNdvi(fieldKey, checkbox.checked, select.value);
          checkbox.addEventListener("change", refresh);
          select.addEventListener("change", refresh);

          controls.append(toggle, select);
          row.appendChild(controls);
        }

        section.appendChild(row);
      }
      list.appendChild(section);
    }

    const fitAll = () => {
      if (MAP_DATA.bounds && MAP_DATA.bounds.length === 2) {
        map.fitBounds(MAP_DATA.bounds, { padding: [30, 30] });
      }
    };
    document.getElementById("fit-all").addEventListener("click", fitAll);
    fitAll();
    updateLegend();
  }

  try {
    init();
  } catch (err) {
    console.error(err);
    showFatal(err && err.message ? err.message : String(err));
  }
</script>
</body>
</html>
"""


def _collect_payload(
    grower_slugs: list[str],
    *,
    simplify_tolerance: float,
    title: str,
    ndvi_year: int,
    include_ndvi: bool,
    ndvi_asset_dir: Path,
    ndvi_cache: dict[Any, Any],
    ndvi_max_size: int,
) -> tuple[dict[str, Any], list[str]]:
    growers: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    sources: list[str] = []

    for grower_slug in grower_slugs:
        farms_root = grower_dir(grower_slug) / "farms"
        farm_slugs = sorted(
            path.name
            for path in farms_root.iterdir()
            if path.is_dir() and farm_boundary_path(grower_slug, path.name).exists()
        ) if farms_root.exists() else []
        if not farm_slugs:
            raise SystemExit(
                f"no farm field boundaries for grower '{grower_slug}' under {farms_root}"
            )

        grower_name = _grower_name(grower_slug)
        farms: list[dict[str, Any]] = []
        grower_features: list[dict[str, Any]] = []
        for farm_slug in farm_slugs:
            farm_features, farm_sources = _load_farm_fields(
                grower_slug,
                grower_name,
                farm_slug,
                simplify_tolerance=simplify_tolerance,
            )
            farms.append(
                {
                    "slug": farm_slug,
                    "name": _farm_name(grower_slug, farm_slug),
                    "field_count": len(farm_features),
                }
            )
            grower_features.extend(farm_features)
            sources.extend(farm_sources)

        if not grower_features:
            print(f"  warn  {grower_slug}: no fields with geometry; skipping grower")
            continue

        growers.append(
            {
                "slug": grower_slug,
                "name": grower_name,
                "farms": farms,
                "farm_count": len(farms),
                "field_count": len(grower_features),
                "bounds": _bounds(grower_features),
            }
        )
        features.extend(grower_features)

    if not features:
        raise SystemExit("no fields with geometry found for the selected growers")

    features.sort(
        key=lambda feature: (
            feature["properties"]["grower_slug"],
            feature["properties"]["farm_slug"],
            feature["properties"]["id"],
        )
    )
    # Stable colors by global index so repeated runs stay byte-identical.
    for index, feature in enumerate(features):
        feature["properties"]["color"] = PALETTE[index % len(PALETTE)]

    payload: dict[str, Any] = {
        "title": title,
        "growers": growers,
        "features": features,
        "bounds": _bounds(features),
    }

    if include_ndvi:
        ndvi = _collect_ndvi(
            features,
            year=ndvi_year,
            asset_dir=ndvi_asset_dir,
            cache=ndvi_cache,
            max_size=ndvi_max_size,
        )
        if ndvi:
            payload["ndvi"] = ndvi

    return payload, sources


def _write_map(
    payload: dict[str, Any],
    sources: list[str],
    output_path: Path,
    manifest_path: Path,
    *,
    title: str,
    simplify_tolerance: float,
    extra_manifest: dict[str, Any] | None = None,
    embed_ndvi: bool = False,
) -> None:
    # Copy so the same payload can be written as both external and standalone.
    payload = copy.deepcopy(payload)
    ndvi = payload.get("ndvi")
    ndvi_manifest: dict[str, Any] | None = None
    if ndvi and ndvi.get("layers"):
        images = []
        for layer in ndvi["layers"]:
            image = Path(layer["image"])
            if embed_ndvi:
                encoded = base64.b64encode(image.read_bytes()).decode("ascii")
                layer["url"] = "data:image/png;base64," + encoded
            else:
                layer["url"] = Path(os.path.relpath(image, output_path.parent)).as_posix()
            images.append(
                {
                    "field_key": layer["field_key"],
                    "date": layer["date"],
                    "image": _display_path(image),
                    "bytes": image.stat().st_size,
                    "sha256": _sha256(image),
                }
            )
            layer.pop("image", None)
        ndvi_manifest = {
            "year": ndvi["year"],
            "sensor": ndvi["sensor"],
            "vmin": ndvi["vmin"],
            "vmax": ndvi["vmax"],
            "layer_count": len(ndvi["layers"]),
            "dates": ndvi["dates"],
            "embedded": embed_ndvi,
            "total_bytes": sum(item["bytes"] for item in images),
            "images": images,
        }

    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    gradient, ticks = _ndvi_legend()
    document = (
        HTML_TEMPLATE.replace("__TITLE__", html.escape(title))
        .replace("__MAP_DATA__", encoded)
        .replace("__ESRI__", ESRI_WORLD_IMAGERY)
        .replace("__ESRI_ATTRIBUTION__", ESRI_ATTRIBUTION)
        .replace("__PALETTE__", json.dumps(list(PALETTE)))
        .replace("__NDVI_GRADIENT__", gradient)
        .replace("__NDVI_TICKS__", ticks)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")

    sources = sorted(set(sources))
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "script": "render_grower_web_map.py",
        "title": title,
        "output": _display_path(output_path),
        "output_bytes": output_path.stat().st_size,
        "grower_count": len(payload["growers"]),
        "field_count": len(payload["features"]),
        "growers": payload["growers"],
        "basemap": {
            "default": "esri_world_imagery",
            "url": ESRI_WORLD_IMAGERY,
        },
        "simplify_tolerance_degrees": simplify_tolerance,
        "sources": [
            {"path": _display_path(Path(source)), "sha256": _sha256(Path(source))}
            for source in sources
        ],
    }
    if ndvi_manifest is not None:
        manifest["ndvi"] = ndvi_manifest
    manifest["standalone"] = embed_ndvi
    if extra_manifest:
        manifest.update(extra_manifest)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _standalone_path(path: Path) -> Path:
    """Return the single-file variant path (``*_standalone`` before the suffix)."""
    return path.with_name(f"{path.stem}_standalone{path.suffix}")


def _write_variants(
    payload: dict[str, Any],
    sources: list[str],
    output_path: Path,
    manifest_path: Path,
    *,
    title: str,
    simplify_tolerance: float,
    extra_manifest: dict[str, Any] | None,
    standalone: bool,
) -> Path | None:
    """Write the external-asset map plus, when requested, an embedded copy."""
    _write_map(
        payload,
        sources,
        output_path,
        manifest_path,
        title=title,
        simplify_tolerance=simplify_tolerance,
        extra_manifest=extra_manifest,
    )
    if not standalone or not payload.get("ndvi", {}).get("layers"):
        return None
    standalone_path = _standalone_path(output_path)
    _write_map(
        payload,
        sources,
        standalone_path,
        _standalone_path(manifest_path),
        title=title,
        simplify_tolerance=simplify_tolerance,
        extra_manifest={**(extra_manifest or {}), "standalone": True},
        embed_ndvi=True,
    )
    return standalone_path


def _discover_growers() -> list[str]:
    if not GROWERS_ROOT.exists():
        return []
    return sorted(
        path.name
        for path in GROWERS_ROOT.iterdir()
        if path.is_dir() and (path / "farms").is_dir()
    )


def _report(
    output_path: Path,
    manifest_path: Path,
    field_count: int,
    ndvi_count: int,
    standalone_path: Path | None = None,
) -> None:
    size_kb = output_path.stat().st_size / 1024
    ndvi_note = f", {ndvi_count} NDVI overlays" if ndvi_count else ""
    print(f"  ok    {field_count} fields{ndvi_note} -> {output_path} ({size_kb:.1f} KB)")
    print(f"        manifest: {manifest_path}")
    if standalone_path is not None and standalone_path.exists():
        standalone_kb = standalone_path.stat().st_size / 1024
        print(f"        standalone: {standalone_path} ({standalone_kb:.1f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--grower-slug",
        action="append",
        default=None,
        help="Grower slug to render (repeatable). Defaults to every grower with farms.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional absolute output directory override for the HTML files.",
    )
    parser.add_argument(
        "--title",
        default="My Farm Advisor — Grower Field Map",
        help="Title recorded in the map header and manifest.",
    )
    parser.add_argument(
        "--simplify-tolerance",
        type=float,
        default=0.0,
        help="Optional shapely simplify tolerance in degrees (0 keeps the exact pipeline polygons).",
    )
    parser.add_argument(
        "--ndvi-year",
        type=int,
        default=2021,
        help="Sentinel NDVI scene year to render as overlays (default 2021).",
    )
    parser.add_argument(
        "--ndvi-max-size",
        type=int,
        default=NDVI_MAX_SIZE,
        help="Maximum NDVI overlay image dimension in pixels (default 512).",
    )
    parser.add_argument(
        "--no-ndvi",
        action="store_true",
        help="Skip Sentinel NDVI overlays and render field boundaries only.",
    )
    parser.add_argument(
        "--no-standalone",
        action="store_true",
        help=(
            "Skip the single-file *_standalone.html variant that embeds NDVI "
            "images for download."
        ),
    )
    parser.add_argument(
        "--no-combined",
        action="store_true",
        help="Skip the combined all-growers map.",
    )
    parser.add_argument(
        "--no-per-grower",
        action="store_true",
        help="Skip the individual per-grower maps.",
    )
    args = parser.parse_args()

    grower_slugs = args.grower_slug or _discover_growers()
    if not grower_slugs:
        raise SystemExit(f"No growers found under {GROWERS_ROOT}")

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    ndvi_cache: dict[Any, Any] = {}
    include_ndvi = not args.no_ndvi
    standalone = not args.no_standalone

    print("=" * 60)
    print("  Grower interactive web map")
    print(f"  Runtime: {DATA_ROOT}")
    if include_ndvi:
        print(f"  NDVI: Sentinel {args.ndvi_year} scenes next to each map")
        if standalone:
            print("  Standalone: *_standalone.html embeds NDVI for single-file download")
    print("=" * 60)

    def collect(
        slugs: list[str], title: str, asset_dir: Path
    ) -> tuple[dict[str, Any], list[str]]:
        return _collect_payload(
            slugs,
            simplify_tolerance=args.simplify_tolerance,
            title=title,
            ndvi_year=args.ndvi_year,
            include_ndvi=include_ndvi,
            ndvi_asset_dir=asset_dir,
            ndvi_cache=ndvi_cache,
            ndvi_max_size=args.ndvi_max_size,
        )

    def ndvi_count(payload: dict[str, Any]) -> int:
        return len(payload.get("ndvi", {}).get("layers", []))

    failures = 0
    rendered = 0

    if not args.no_per_grower:
        for grower_slug in grower_slugs:
            output_path = (
                output_dir / f"{grower_slug}_fields_map.html"
                if output_dir is not None
                else grower_dir(grower_slug) / "maps" / f"{grower_slug}_fields_map.html"
            )
            manifest_path = grower_dir(grower_slug) / "manifests" / "grower_web_map.json"
            try:
                payload, sources = collect([grower_slug], args.title, output_path.parent / "ndvi")
            except SystemExit as exc:
                print(f"  skip  {grower_slug}: {exc}")
                failures += 1
                continue

            grower = payload["growers"][0]
            title = f"{grower['name']} — Field Map"
            payload["title"] = title
            print(f"  {grower_slug}")
            standalone_path = _write_variants(
                payload,
                sources,
                output_path,
                manifest_path,
                title=title,
                simplify_tolerance=args.simplify_tolerance,
                extra_manifest={
                    "grower_slug": grower_slug,
                    "grower_name": grower["name"],
                    "farms": grower["farms"],
                    "combined_map": not args.no_combined and len(grower_slugs) > 1,
                },
                standalone=standalone,
            )
            _report(
                output_path,
                manifest_path,
                len(payload["features"]),
                ndvi_count(payload),
                standalone_path,
            )
            rendered += 1

    if not args.no_combined and len(grower_slugs) > 1:
        output_path = (
            output_dir / "all-growers_fields_map.html"
            if output_dir is not None
            else DATA_ROOT / "maps" / "all-growers_fields_map.html"
        )
        manifest_path = DATA_ROOT / "manifests" / "all_growers_web_map.json"
        try:
            payload, sources = collect(
                grower_slugs, args.title, output_path.parent / "ndvi"
            )
        except SystemExit as exc:
            print(f"  skip  combined: {exc}")
            failures += 1
        else:
            print("  combined")
            standalone_path = _write_variants(
                payload,
                sources,
                output_path,
                manifest_path,
                title=args.title,
                simplify_tolerance=args.simplify_tolerance,
                extra_manifest={"grower_slugs": [g["slug"] for g in payload["growers"]]},
                standalone=standalone,
            )
            _report(
                output_path,
                manifest_path,
                len(payload["features"]),
                ndvi_count(payload),
                standalone_path,
            )
            rendered += 1

    print("=" * 60)
    if rendered == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
