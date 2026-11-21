#!/usr/bin/env python3
"""Run the reusable field-level EDA across the demo growers.

Usage:
    DATA_PIPELINE_DATA_ROOT=/abs/path \\
        python data-pipeline/src/scripts/run_field_eda.py \\
        [--grower il-demo-grower ...] [--output-dir PATH] [--dry-run]

The command discovers growers with complete boundary, weather, and CDL
composition inputs, builds the category metrics, and writes static tables,
PNG figures, and a manifest under the configured output directory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bootstrap_runtime import ensure_runtime_environment

ensure_runtime_environment()

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

from lib.paths import (  # noqa: E402
    DATA_ROOT,
    GROWERS_ROOT,
    farm_boundary_path,
    farm_tables_dir,
    farm_weather_path,
)
from reporting_bootstrap import ensure_skill_path  # noqa: E402

DEFAULT_OUTPUT_DIR = DATA_ROOT / "eda" / "field-eda"
DEFAULT_COUNTIES_PATH = (
    DATA_ROOT / "shared" / "geoadmin" / "l2_counties" / "counties_usa.parquet"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the static field-level EDA for one or more growers"
    )
    parser.add_argument(
        "--grower",
        action="append",
        dest="growers",
        help="Grower slug to include; repeat for multiple. Defaults to all growers.",
    )
    parser.add_argument(
        "--farm",
        action="append",
        dest="farms",
        help="Farm slug filter; repeat for multiple. Defaults to every eligible farm.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--cdl-start-year", type=int, default=2019, help="First CDL year (default: 2019)"
    )
    parser.add_argument(
        "--cdl-end-year", type=int, default=2023, help="Last CDL year (default: 2023)"
    )
    parser.add_argument(
        "--weather-start-year",
        type=int,
        default=2021,
        help="First weather year (default: 2021)",
    )
    parser.add_argument(
        "--weather-end-year",
        type=int,
        default=2025,
        help="Last weather year (default: 2025)",
    )
    parser.add_argument(
        "--dpi", type=int, default=200, help="Figure resolution (default: 200)"
    )
    parser.add_argument(
        "--counties-path",
        type=Path,
        default=DEFAULT_COUNTIES_PATH,
        help=f"County context parquet (default: {DEFAULT_COUNTIES_PATH})",
    )
    parser.add_argument(
        "--no-counties",
        action="store_true",
        help="Draw maps without county context",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the discovered inputs and exit without writing outputs",
    )
    return parser.parse_args()


def _eligible_farms(
    grower_slug: str,
    weather_start_year: int,
    weather_end_year: int,
    cdl_start_year: int,
    cdl_end_year: int,
) -> list[str]:
    farms_root = GROWERS_ROOT / grower_slug / "farms"
    if not farms_root.exists():
        return []
    eligible: list[str] = []
    for farm_dir in sorted(farms_root.iterdir()):
        if not farm_dir.is_dir():
            continue
        farm_slug = farm_dir.name
        boundary = farm_boundary_path(grower_slug, farm_slug)
        weather = farm_weather_path(
            grower_slug, farm_slug, weather_start_year, weather_end_year
        )
        compositions = sorted(
            farm_tables_dir(grower_slug, farm_slug).glob(
                f"*_cdl_{cdl_start_year}_{cdl_end_year}_full_composition.csv"
            )
        )
        if boundary.exists() and weather.exists() and compositions:
            eligible.append(farm_slug)
    return eligible


def discover(args: argparse.Namespace) -> list[tuple[str, str]]:
    if args.growers:
        growers = list(dict.fromkeys(args.growers))
    else:
        growers = (
            sorted(path.name for path in GROWERS_ROOT.iterdir() if path.is_dir())
            if GROWERS_ROOT.exists()
            else []
        )
    pairs: list[tuple[str, str]] = []
    missing: list[str] = []
    for grower in growers:
        farms = _eligible_farms(
            grower,
            args.weather_start_year,
            args.weather_end_year,
            args.cdl_start_year,
            args.cdl_end_year,
        )
        if args.farms:
            farms = [farm for farm in farms if farm in set(args.farms)]
        if not farms:
            missing.append(grower)
            continue
        pairs.extend((grower, farm) for farm in farms)
    if missing:
        print(
            f"WARNING: no eligible farms for grower(s): {', '.join(missing)}",
            file=sys.stderr,
        )
    if not pairs:
        raise SystemExit(
            "No farms with boundary, weather, and CDL composition inputs were found."
        )
    return pairs


def _load_farm_inputs(
    grower_slug: str,
    farm_slug: str,
    args: argparse.Namespace,
    field_eda_module,
):
    boundary_path = farm_boundary_path(grower_slug, farm_slug)
    weather_path = farm_weather_path(
        grower_slug, farm_slug, args.weather_start_year, args.weather_end_year
    )
    tables = farm_tables_dir(grower_slug, farm_slug)
    composition_candidates = sorted(
        tables.glob(f"*_cdl_{args.cdl_start_year}_{args.cdl_end_year}_full_composition.csv")
    )
    if not composition_candidates:
        raise SystemExit(
            f"No CDL composition for {grower_slug}/{farm_slug} "
            f"({args.cdl_start_year}-{args.cdl_end_year})"
        )
    composition_path = composition_candidates[0]
    rotation_candidates = sorted(tables.glob("*_crop_rotation.csv"))

    fields = gpd.read_file(boundary_path)
    weather = pd.read_csv(weather_path, parse_dates=["date"])
    composition = pd.read_csv(composition_path)
    rotation = (
        pd.read_csv(rotation_candidates[0]) if rotation_candidates else None
    )

    for frame, label in ((fields, "boundaries"), (weather, "weather"), (composition, "CDL")):
        if "field_id" not in frame.columns:
            raise SystemExit(
                f"{grower_slug}/{farm_slug}: {label} input is missing field_id"
            )

    return field_eda_module.FarmData(
        grower_slug=grower_slug,
        farm_slug=farm_slug,
        fields=fields,
        weather=weather,
        composition=composition,
        rotation=rotation,
        inputs={
            "boundaries": str(boundary_path),
            "weather": str(weather_path),
            "composition": str(composition_path),
            "rotation": str(rotation_candidates[0]) if rotation_candidates else "",
        },
    )


def _load_counties(
    path: Path, fields: gpd.GeoDataFrame, enabled: bool
) -> gpd.GeoDataFrame | None:
    if not enabled or not path.exists() or fields.empty:
        return None
    columns = ["state_fips", "county_name", "geometry"]
    counties = gpd.read_parquet(path, columns=columns)
    if fields.crs is None:
        fields = fields.set_crs("EPSG:4326")
    counties = counties.to_crs(fields.crs)
    if "state_fips" in fields.columns:
        state_fips = {str(value) for value in fields["state_fips"].dropna().unique()}
        counties = counties.loc[counties["state_fips"].astype(str).isin(state_fips)]
    projected_fields = fields.to_crs("EPSG:5070")
    projected_counties = counties.to_crs("EPSG:5070")
    buffered = projected_fields.geometry.buffer(15000.0)
    footprint = (
        buffered.union_all() if hasattr(buffered, "union_all") else buffered.unary_union
    )
    selected = projected_counties.loc[projected_counties.geometry.intersects(footprint)]
    return selected.to_crs(fields.crs).copy()


def main() -> int:
    args = parse_args()
    ensure_skill_path("field-eda")

    import field_eda as field_eda_module

    pairs = discover(args)
    print("Field-level EDA plan")
    for grower, farm in pairs:
        print(f"  - {grower}/{farm}")
    print(f"  output: {args.output_dir}")

    if args.dry_run:
        print("Dry run: no outputs written.")
        return 0

    farms = [
        _load_farm_inputs(grower, farm, args, field_eda_module)
        for grower, farm in pairs
    ]
    combined_fields = gpd.GeoDataFrame(
        pd.concat([farm.fields for farm in farms], ignore_index=True),
        geometry="geometry",
        crs=farms[0].fields.crs,
    )
    counties = _load_counties(args.counties_path, combined_fields, not args.no_counties)
    if counties is None and not args.no_counties:
        print(f"WARNING: county context unavailable at {args.counties_path}", file=sys.stderr)

    params = field_eda_module.EdaParams(
        output_dir=args.output_dir,
        cdl_start_year=args.cdl_start_year,
        cdl_end_year=args.cdl_end_year,
        weather_start_year=args.weather_start_year,
        weather_end_year=args.weather_end_year,
        dpi=args.dpi,
    )
    manifest = field_eda_module.run_eda(farms, params, counties=counties)

    print("\nTables")
    for record in manifest["tables"]:
        print(f"  {record['name']:<32} {record['rows']:>6} rows")
    print("\nFigures")
    for record in manifest["figures"]:
        print(f"  {record['name']}")
    headline = manifest["headline"]
    print(
        f"\nHeadline: {headline['fields']} fields across {headline['growers']} growers, "
        f"{headline['total_area_acres']:,.0f} acres"
    )
    print(f"Manifest: {manifest['manifest_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
