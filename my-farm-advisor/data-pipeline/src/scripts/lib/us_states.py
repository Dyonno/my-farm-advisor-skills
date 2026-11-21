"""Minimal US state name/abbreviation to FIPS helpers.

The data pipeline stores state context on field boundaries as either a
two-letter abbreviation (``state``) or a two-digit FIPS code
(``state_fips``). CDL raster routing needs the FIPS code, so this module is the
single place that resolves the supported spellings.
"""

from __future__ import annotations

import math

STATE_TABLE: dict[str, tuple[str, str]] = {
    "AL": ("01", "Alabama"),
    "AK": ("02", "Alaska"),
    "AZ": ("04", "Arizona"),
    "AR": ("05", "Arkansas"),
    "CA": ("06", "California"),
    "CO": ("08", "Colorado"),
    "CT": ("09", "Connecticut"),
    "DE": ("10", "Delaware"),
    "DC": ("11", "District of Columbia"),
    "FL": ("12", "Florida"),
    "GA": ("13", "Georgia"),
    "HI": ("15", "Hawaii"),
    "ID": ("16", "Idaho"),
    "IL": ("17", "Illinois"),
    "IN": ("18", "Indiana"),
    "IA": ("19", "Iowa"),
    "KS": ("20", "Kansas"),
    "KY": ("21", "Kentucky"),
    "LA": ("22", "Louisiana"),
    "ME": ("23", "Maine"),
    "MD": ("24", "Maryland"),
    "MA": ("25", "Massachusetts"),
    "MI": ("26", "Michigan"),
    "MN": ("27", "Minnesota"),
    "MS": ("28", "Mississippi"),
    "MO": ("29", "Missouri"),
    "MT": ("30", "Montana"),
    "NE": ("31", "Nebraska"),
    "NV": ("32", "Nevada"),
    "NH": ("33", "New Hampshire"),
    "NJ": ("34", "New Jersey"),
    "NM": ("35", "New Mexico"),
    "NY": ("36", "New York"),
    "NC": ("37", "North Carolina"),
    "ND": ("38", "North Dakota"),
    "OH": ("39", "Ohio"),
    "OK": ("40", "Oklahoma"),
    "OR": ("41", "Oregon"),
    "PA": ("42", "Pennsylvania"),
    "RI": ("44", "Rhode Island"),
    "SC": ("45", "South Carolina"),
    "SD": ("46", "South Dakota"),
    "TN": ("47", "Tennessee"),
    "TX": ("48", "Texas"),
    "UT": ("49", "Utah"),
    "VT": ("50", "Vermont"),
    "VA": ("51", "Virginia"),
    "WA": ("53", "Washington"),
    "WV": ("54", "West Virginia"),
    "WI": ("55", "Wisconsin"),
    "WY": ("56", "Wyoming"),
}

STATE_FIPS: dict[str, str] = {abbrev: fips for abbrev, (fips, _) in STATE_TABLE.items()}
STATE_NAMES: dict[str, str] = {fips: name for (fips, name) in STATE_TABLE.values()}
_NAME_TO_FIPS: dict[str, str] = {name.casefold(): fips for fips, name in STATE_NAMES.items()}


def state_fips(value: object) -> str | None:
    """Return a two-digit state FIPS code for an abbreviation, name, or code."""
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (int, float)):
        if value != int(value):
            return None
        value = int(value)
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return raw.zfill(2) if len(raw) <= 2 else None
    abbrev = raw.upper().replace(".", "")
    if abbrev in STATE_FIPS:
        return STATE_FIPS[abbrev]
    return _NAME_TO_FIPS.get(raw.casefold())


def state_name(value: object) -> str | None:
    """Return the full state name for a supported abbreviation, name, or code."""
    fips = state_fips(value)
    return STATE_NAMES.get(fips) if fips else None
