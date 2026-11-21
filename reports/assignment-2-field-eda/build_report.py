#!/usr/bin/env python3
"""Build the one-time Assignment 2 field-level EDA report PDF.

The report is assembled from an existing field-eda run: the manifest, the CSV
tables, and the PNG figures. It is deliberately outside the reusable subskill
and writes a single self-contained PDF that can be committed and opened from a
pull request.

Usage:
    DATA_PIPELINE_DATA_ROOT=/abs/runtime/root \
        /abs/runtime/root/data-pipeline/.venv/bin/python \
        reports/assignment-2-field-eda/build_report.py
"""

from __future__ import annotations

import argparse
import io
import os
import zlib
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from PIL import Image

PAGE_W = 612.0
PAGE_H = 792.0
MARGIN = 54.0
BOTTOM = 64.0
CONTENT_W = PAGE_W - 2 * MARGIN
ACCENT = (0.0, 0.45, 0.70)
DARK = (0.08, 0.13, 0.18)
BODY = (0.16, 0.16, 0.16)
MUTED = (0.42, 0.44, 0.47)
LIGHT_RULE = (0.82, 0.84, 0.86)
ZEBRA = (0.955, 0.965, 0.975)

# Helvetica AFM widths (1/1000 em) for ASCII.
_HELV = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584,
    "?": 556, "@": 1015, "A": 667, "B": 667, "C": 722, "D": 722, "E": 667,
    "F": 611, "G": 778, "H": 722, "I": 278, "J": 500, "K": 667, "L": 556,
    "M": 833, "N": 722, "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667,
    "T": 611, "U": 722, "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556, "`": 333, "a": 556,
    "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556, "h": 556,
    "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556, "o": 556,
    "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556, "v": 500,
    "w": 722, "x": 500, "y": 500, "z": 500, "{": 334, "|": 260, "}": 334,
    "~": 584,
}
for _digit in "0123456789":
    _HELV[_digit] = 556


def text_width(text: str, size: float, bold: bool = False) -> float:
    width = sum(_HELV.get(char, 556) for char in text) * size / 1000.0
    return width * (1.06 if bold else 1.0)


def wrap(text: str, size: float, width: float, bold: bool = False) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = word if not current else f"{current} {word}"
        if text_width(candidate, size, bold) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class Pdf:
    """Minimal PDF writer: Helvetica text plus DCT (JPEG) images."""

    def __init__(self) -> None:
        self.pages: list[str] = []
        self.images: list[tuple[str, bytes, int, int]] = []

    def image_name(self, key: str, data: bytes, width: int, height: int) -> str:
        for name, existing, _, _ in self.images:
            if existing == data:
                return name
        name = f"Im{len(self.images) + 1}"
        self.images.append((name, data, width, height))
        return name

    def add_page(self, content: str) -> None:
        self.pages.append(content)

    def write(self, path: Path, metadata: dict[str, str]) -> None:
        objects: list[bytes | None] = [None]

        def add(payload: bytes) -> int:
            objects.append(payload)
            return len(objects) - 1

        font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

        image_ids: dict[str, int] = {}
        for name, data, width, height in self.images:
            header = (
                f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
                f"/Length {len(data)} >>\nstream\n"
            ).encode("ascii")
            image_ids[name] = add(header + data + b"\nendstream")

        xobjects = " ".join(f"/{name} {oid} 0 R" for name, oid in image_ids.items())
        resources = (
            f"<< /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> "
            f"/XObject << {xobjects} >> >>"
        )

        page_ids: list[int] = []
        for content in self.pages:
            compressed = zlib.compress(content.encode("latin-1"), 9)
            content_id = add(
                f"<< /Length {len(compressed)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
                + compressed
                + b"\nendstream"
            )
            page_id = add(
                (
                    f"<< /Type /Page /Parent PAGES_ID 0 R /MediaBox [0 0 {PAGE_W:.0f} {PAGE_H:.0f}] "
                    f"/Resources {resources} /Contents {content_id} 0 R >>"
                ).encode("ascii")
            )
            page_ids.append(page_id)

        pages_id = add(
            (
                f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] "
                f"/Count {len(page_ids)} >>"
            ).encode("ascii")
        )
        catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))
        info = " ".join(
            f"/{key} ({escape(value)})" for key, value in metadata.items()
        )
        info_id = add(f"<< {info} >>".encode("latin-1"))

        # Point the page objects at the real page-tree id, now that it exists.
        parent = f"/Parent {pages_id} 0 R".encode()
        for page_id in page_ids:
            payload = objects[page_id]
            assert payload is not None
            objects[page_id] = payload.replace(b"/Parent PAGES_ID 0 R", parent)

        buffer = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: list[int] = []
        for index in range(1, len(objects)):
            offsets.append(len(buffer))
            buffer += f"{index} 0 obj\n".encode("ascii")
            buffer += objects[index] or b""
            buffer += b"\nendobj\n"
        xref_at = len(buffer)
        buffer += f"xref\n0 {len(objects)}\n".encode("ascii")
        buffer += b"0000000000 65535 f \n"
        for offset in offsets:
            buffer += f"{offset:010d} 00000 n \n".encode("ascii")
        buffer += (
            f"trailer\n<< /Size {len(objects)} /Root {catalog_id} 0 R "
            f"/Info {info_id} 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
        ).encode("ascii")
        path.write_bytes(bytes(buffer))


class Report:
    def __init__(self, pdf: Pdf) -> None:
        self.pdf = pdf
        self.content: list[str] = []
        self.y = PAGE_H - 64.0
        self.page_number = 0
        self._start_page(header=False)

    def _rule(self, y: float, color: tuple[float, float, float], width: float = 0.7) -> None:
        r, g, b = color
        self.content.append(
            f"{width:.2f} w {r:.3f} {g:.3f} {b:.3f} RG {MARGIN:.2f} {y:.2f} m "
            f"{PAGE_W - MARGIN:.2f} {y:.2f} l S"
        )

    def _fill(self, x: float, y: float, w: float, h: float, color: tuple[float, float, float]) -> None:
        r, g, b = color
        self.content.append(f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def _start_page(self, header: bool = True) -> None:
        self.page_number += 1
        self.content = []
        self.y = PAGE_H - 64.0
        if header:
            self.content.append(
                f"BT /F1 7.6 Tf 0.42 0.44 0.47 rg 1 0 0 1 {MARGIN:.2f} {PAGE_H - 38:.2f} Tm "
                "(Field-Level EDA  /  Assignment 2) Tj ET"
            )
            self.content.append(
                f"BT /F1 7.6 Tf 0.42 0.44 0.47 rg 1 0 0 1 {PAGE_W - MARGIN - 74:.2f} "
                f"{PAGE_H - 38:.2f} Tm (My Farm Advisor) Tj ET"
            )
            self._rule(PAGE_H - 46, LIGHT_RULE)
        self._rule(44, LIGHT_RULE)
        self.content.append(
            f"BT /F1 7.4 Tf 0.42 0.44 0.47 rg 1 0 0 1 {MARGIN:.2f} 30 Tm "
            "(Generated from the field-eda manifest and static EDA outputs) Tj ET"
        )
        self.content.append(
            f"BT /F2 8 Tf 0.24 0.27 0.30 rg 1 0 0 1 {PAGE_W - MARGIN - 8:.2f} 30 Tm "
            f"({self.page_number}) Tj ET"
        )

    def page_break(self) -> None:
        self.pdf.add_page("\n".join(self.content))
        self._start_page()

    def ensure(self, height: float) -> None:
        if self.y - height < BOTTOM:
            self.page_break()

    def text(
        self,
        value: str,
        size: float = 9.6,
        bold: bool = False,
        color: tuple[float, float, float] = BODY,
        leading: float = 1.42,
        space_after: float = 5.0,
        x: float = MARGIN,
        width: float = CONTENT_W,
    ) -> None:
        lines = wrap(value, size, width, bold=bold)
        for line in lines:
            self.ensure(size * leading)
            r, g, b = color
            font = "F2" if bold else "F1"
            baseline = self.y - size * 0.82
            self.content.append(
                f"BT /{font} {size} Tf {r:.3f} {g:.3f} {b:.3f} rg "
                f"1 0 0 1 {x:.2f} {baseline:.2f} Tm ({escape(line)}) Tj ET"
            )
            self.y -= size * leading
        self.y -= space_after

    def heading(self, value: str) -> None:
        self.ensure(52)
        self.y -= 2
        self.text(value, size=14.5, bold=True, color=DARK, leading=1.2, space_after=4)
        r, g, b = ACCENT
        self.content.append(
            f"2 w {r:.3f} {g:.3f} {b:.3f} RG {MARGIN:.2f} {self.y + 2:.2f} m "
            f"{MARGIN + 34:.2f} {self.y + 2:.2f} l S"
        )
        self.y -= 8

    def subheading(self, value: str) -> None:
        self.ensure(30)
        self.y -= 3
        self.text(value, size=10.5, bold=True, color=DARK, leading=1.25, space_after=3)

    def bullets(self, items: list[str], size: float = 9.2, leading: float = 1.38) -> None:
        for item in items:
            lines = wrap(item, size, CONTENT_W - 14)
            self.ensure(len(lines) * size * leading + 4)
            top = self.y
            self._fill(MARGIN + 2, top - size * 0.62, 2.6, 2.6, ACCENT)
            for index, line in enumerate(lines):
                baseline = self.y - size * 0.82
                self.content.append(
                    f"BT /F1 {size} Tf 0.16 0.16 0.16 rg 1 0 0 1 {MARGIN + 13:.2f} "
                    f"{baseline:.2f} Tm ({escape(line)}) Tj ET"
                )
                self.y -= size * leading
            self.y -= 3
        self.y -= 2

    def caption(self, label: str, body: str) -> None:
        lines = wrap(body, 8.4, CONTENT_W, bold=False)
        self.ensure(len(lines) * 8.4 * 1.35 + 22)
        r, g, b = ACCENT
        self.content.append(
            f"BT /F2 7.2 Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {MARGIN:.2f} "
            f"{self.y - 7.0:.2f} Tm ({escape(label.upper())}) Tj ET"
        )
        self.y -= 11.5
        for line in lines:
            self.content.append(
                f"BT /F1 8.4 Tf 0.30 0.31 0.33 rg 1 0 0 1 {MARGIN:.2f} "
                f"{self.y - 6.9:.2f} Tm ({escape(line)}) Tj ET"
            )
            self.y -= 8.4 * 1.35
        self.y -= 9

    def image(self, path: Path, width_in: float, label: str, body: str, dpi: int = 122) -> None:
        with Image.open(path) as source:
            image = source.convert("RGB")
            target_w = max(320, int(width_in * dpi))
            target_h = max(1, round(image.height * target_w / image.width))
            resized = image.resize((target_w, target_h), Image.LANCZOS)
            buffer = io.BytesIO()
            resized.save(buffer, "JPEG", quality=72, optimize=True, progressive=True)
            data = buffer.getvalue()
        display_w = width_in * 72.0
        display_h = display_w * target_h / target_w
        caption_lines = wrap(body, 8.4, CONTENT_W)
        needed = display_h + len(caption_lines) * 8.4 * 1.35 + 34
        self.ensure(needed)
        name = self.pdf.image_name(str(path), data, target_w, target_h)
        x = (PAGE_W - display_w) / 2.0
        bottom = self.y - display_h
        self.content.append(
            f"q {display_w:.2f} 0 0 {display_h:.2f} {x:.2f} {bottom:.2f} cm /{name} Do Q"
        )
        self.y = bottom - 9
        self.caption(label, body)

    def table(
        self,
        rows: list[list[str]],
        widths: list[float],
        size: float = 8.6,
        header: bool = True,
        align_right: set[int] | None = None,
    ) -> None:
        align_right = align_right or set()
        leading = 1.28
        prepared: list[list[list[str]]] = []
        heights: list[float] = []
        for row in rows:
            cells = [wrap(cell, size, widths[index] - 8) for index, cell in enumerate(row)]
            prepared.append(cells)
            heights.append(max(len(cell) for cell in cells) * size * leading + 7.5)
        total = sum(heights)
        self.ensure(total + 4)
        x0 = MARGIN
        for row_index, (cells, height) in enumerate(zip(prepared, heights)):
            top = self.y
            if row_index == 0 and header:
                self._fill(x0, top - height, sum(widths), height, ZEBRA)
            elif row_index % 2 == 0:
                self._fill(x0, top - height, sum(widths), height, (0.985, 0.988, 0.992))
            x = x0
            for column, cell in enumerate(cells):
                bold = row_index == 0 and header
                for line_index, line in enumerate(cell):
                    baseline = top - 4.5 - size * 0.82 - line_index * size * leading
                    if column in align_right and not bold:
                        tx = x + widths[column] - 4 - text_width(line, size, bold)
                    else:
                        tx = x + 4
                    self.content.append(
                        f"BT /{'F2' if bold else 'F1'} {size} Tf "
                        f"{'0.10 0.14 0.18' if bold else '0.20 0.21 0.22'} rg "
                        f"1 0 0 1 {tx:.2f} {baseline:.2f} Tm ({escape(line)}) Tj ET"
                    )
                x += widths[column]
            self._rule(top - height, LIGHT_RULE, 0.45)
            self.y -= height
        self.y -= 10

    def callout(self, title: str, body: str) -> None:
        body_lines = wrap(body, 9.0, CONTENT_W - 28)
        height = 26 + len(body_lines) * 9.0 * 1.38 + 8
        self.ensure(height + 6)
        top = self.y
        self._fill(MARGIN, top - height, CONTENT_W, height, (0.945, 0.972, 0.985))
        self._fill(MARGIN, top - height, 3.4, height, ACCENT)
        self.content.append(
            f"BT /F2 9.0 Tf 0.0 0.32 0.52 rg 1 0 0 1 {MARGIN + 14:.2f} "
            f"{top - 15:.2f} Tm ({escape(title)}) Tj ET"
        )
        y = top - 28
        for line in body_lines:
            self.content.append(
                f"BT /F1 9.0 Tf 0.22 0.23 0.25 rg 1 0 0 1 {MARGIN + 14:.2f} "
                f"{y:.2f} Tm ({escape(line)}) Tj ET"
            )
            y -= 9.0 * 1.38
        self.y = top - height - 10

    def finish(self) -> None:
        self.pdf.add_page("\n".join(self.content))


def fmt_p(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    if value < 0.001:
        return f"{value:.1e}".replace("e-0", "e-").replace("e+0", "e+")
    return f"{value:.3f}"


def fmt_num(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


def metric_row(frame: pd.DataFrame, metric: str, **filters: str) -> pd.Series | None:
    subset = frame.loc[frame["metric"] == metric]
    for column, value in filters.items():
        subset = subset.loc[subset[column] == value]
    return None if subset.empty else subset.iloc[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eda-dir",
        type=Path,
        help="Directory containing manifest.json, tables/, and figures/.",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    default_root = Path(
        os.environ.get("DATA_PIPELINE_DATA_ROOT", Path.home() / "my-farm-advisor-runtime")
    )
    eda_dir = args.eda_dir or (default_root / "data-pipeline/eda/field-eda")
    output = args.output or (
        repo_root / "reports/assignment-2-field-eda/field-eda-report.pdf"
    )
    manifest_path = eda_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tables = eda_dir / "tables"
    figures = eda_dir / "figures"

    boundary = pd.read_csv(tables / "boundary_comparison.csv")
    crop = pd.read_csv(tables / "crop_comparison.csv")
    weather = pd.read_csv(tables / "weather_comparison.csv")
    correlations = pd.read_csv(tables / "weather_correlations.csv")
    profile = pd.read_csv(tables / "field_profile.csv")
    cells = pd.read_csv(tables / "weather_cells.csv")
    rotation = pd.read_csv(tables / "crop_rotation_summary.csv")
    boundary_summary = pd.read_csv(tables / "boundary_grower_summary.csv")
    crop_summary = pd.read_csv(tables / "crop_grower_summary.csv")

    growers = (
        profile.groupby(["grower_slug", "state", "county"], dropna=False)
        .agg(
            fields=("field_id", "nunique"),
            acres=("area_acres", "sum"),
            median_acres=("area_acres", "median"),
            gdd=("mean_gdd_season", "mean"),
            precip=("mean_precip_annual", "mean"),
        )
        .reset_index()
        .sort_values("state")
    )
    grower_cells = cells.groupby("grower_slug")["weather_cell_id"].nunique()
    grower_vertices = profile.groupby("grower_slug")["vertex_count"].median()
    fields_per_cell = cells.groupby(["grower_slug", "weather_cell_id"])["field_id"].nunique()

    area_kw = metric_row(boundary, "area_acres", analysis="kruskal-wallis")
    compact_kw = metric_row(boundary, "compactness", analysis="kruskal-wallis")
    convex_kw = metric_row(boundary, "convexity", analysis="kruskal-wallis")
    crop_cont = metric_row(crop, "continuous_years", analysis="kruskal-wallis")
    crop_chi = metric_row(crop, "crop_transitions", analysis="chi-square")
    gdd_field = metric_row(weather, "gdd_season", level="field")
    gdd_cell = metric_row(weather, "gdd_season", level="weather-cell")
    annual_field = metric_row(weather, "precip_annual", level="field")
    heat_field = metric_row(weather, "heat_days_30", level="field")
    frost_field = metric_row(weather, "frost_free_days", level="field")
    growing_field = metric_row(weather, "precip_growing", level="field")

    continuous = rotation.loc[rotation["corn_years"] == rotation["history_years"]]
    continuous_text = ", ".join(
        f"{slug.split('-')[0].upper()} {int((continuous['grower_slug'] == slug).sum())}/10"
        for slug in sorted(rotation["grower_slug"].unique())
    )

    positive = correlations.loc[correlations["rho"].idxmax()]
    negative = correlations.loc[correlations["rho"].idxmin()]
    significant = int((correlations["p_bh"] < 0.05).sum())

    generated_at = manifest.get("generated_at", "unknown")
    headline = manifest.get("headline", {})
    total_acres = float(headline.get("total_area_acres", profile["area_acres"].sum()))
    total_fields = int(headline.get("fields", profile["field_id"].nunique()))
    total_growers = int(headline.get("growers", profile["grower_slug"].nunique()))

    pdf = Pdf()
    report = Report(pdf)

    # --- Cover ------------------------------------------------------------
    report.content.append(f"q 0.0 0.45 0.70 rg 0 {PAGE_H - 12:.2f} {PAGE_W:.2f} 12 re f Q")
    report.y = PAGE_H - 132
    report.text("ASSIGNMENT 2  /  FIELD-LEVEL EDA", size=9, bold=True, color=ACCENT, space_after=10)
    report.text("Field-Level EDA of Three Demo Growers", size=25, bold=True, color=DARK, leading=1.12, space_after=10)
    report.text(
        "Illinois, Iowa, and Nebraska  |  30 fields  |  2019-2025 data windows",
        size=11.5,
        color=MUTED,
        space_after=16,
    )
    report.y -= 4
    report._rule(report.y, ACCENT, 1.2)
    report.y -= 18
    report.text(
        "This report summarizes a reproducible field-level exploratory analysis of three demo "
        "growers in the My Farm Advisor catalog. It uses field boundaries, USDA CDL crop "
        "history, and NASA POWER weather to compare fields over time, across fields within a "
        "grower, and across growers.",
        size=10.4,
        leading=1.5,
        space_after=14,
    )

    stat_labels = [
        (str(total_growers), "growers"),
        (str(total_fields), "fields"),
        (f"{total_acres:,.0f}", "acres"),
        ("15 / 13", "tables / figures"),
    ]
    box_w = (CONTENT_W - 3 * 8) / 4
    top = report.y
    for index, (number, label) in enumerate(stat_labels):
        x = MARGIN + index * (box_w + 8)
        report._fill(x, top - 54, box_w, 54, (0.955, 0.972, 0.985))
        report.content.append(
            f"BT /F2 17 Tf 0.0 0.32 0.52 rg 1 0 0 1 {x + 9:.2f} {top - 24:.2f} Tm "
            f"({escape(number)}) Tj ET"
        )
        report.content.append(
            f"BT /F1 7.8 Tf 0.35 0.38 0.41 rg 1 0 0 1 {x + 9:.2f} {top - 40:.2f} Tm "
            f"({escape(label)}) Tj ET"
        )
    report.y = top - 70

    report.subheading("Contents")
    report.bullets(
        [
            "Dataset scope and grower locations",
            "Comparison levels and methods",
            "Boundary, crop-history, and weather analysis figures",
            "Comparison and correlation analyses",
            "Geospatial maps",
            "Limitations, assumptions, and soil scope",
            "Artifact inventory and headline statistics",
        ],
        size=9.2,
    )
    report.y -= 40
    report.text(
        f"Prepared {datetime.now(UTC).strftime('%d %B %Y')} from the field-eda manifest "
        f"generated {generated_at}.",
        size=8.4,
        color=MUTED,
    )
    report.page_break()

    # --- 1. Scope ---------------------------------------------------------
    report.heading("1. Dataset scope and grower locations")
    report.text(
        "The analysis covers three demo growers, one farm each and 10 fields per farm. The "
        "counties below orient the reader; they are demo locations, not a production survey.",
        space_after=7,
    )
    table_rows = [["Grower", "State", "County", "Fields", "Acres", "Median field", "Season GDD", "Annual precip"]]
    for _, row in growers.iterrows():
        table_rows.append(
            [
                row["grower_slug"].replace("-demo-grower", "").upper(),
                row["state"],
                row["county"],
                str(int(row["fields"])),
                f"{row['acres']:,.0f}",
                f"{row['median_acres']:,.0f}",
                f"{row['gdd']:,.0f}",
                f"{row['precip']:,.0f} mm",
            ]
        )
    report.table(
        table_rows,
        [62, 34, 78, 42, 52, 70, 62, 70],
        size=8.4,
        align_right={3, 4, 5, 6, 7},
    )

    report.image(
        figures / "03_field_map.png",
        6.9,
        "What the map shows",
        "Each panel is one grower's field layout with county context. The three clusters are far "
        "apart (Iroquois County IL, Kossuth County IA, York County NE), so cross-grower "
        "comparisons are state and climate comparisons, not neighborhood comparisons. Panel "
        "scales differ and should not be used to judge absolute field size.",
        dpi=118,
    )

    report.subheading("Data layers and windows")
    report.bullets(
        [
            "Field boundaries: polygons with field_id, crop, state, and county; geometry measured "
            "in EPSG:5070.",
            "Crop history: USDA CDL composition for 2019-2023, collapsed to seven crop groups and "
            "recomputed from pixel counts (1,052 field-year-class rows).",
            "Weather: NASA POWER daily series at field centroids for 2021-2025, aggregated to 150 "
            "field-years and 10 distinct grid cells.",
            "Rotation check: the pipeline-reported crop sequence, used only to validate the CDL "
            "sequence.",
            "Completeness: all 30 fields have five CDL years and five weather years; the 150 "
            "field-years contain no missing values in the metrics reported here.",
        ],
    )
    report.subheading("Headline findings")
    report.bullets(
        [
            "Field size: NE fields are smaller than IA and IL fields, while IA and IL are "
            "indistinguishable. No shape metric separates growers after correction.",
            "Crop history: NE holds 3 of the 4 continuous-corn fields. The remaining fields "
            "alternate corn and soybeans.",
            "Weather: NE is hotter and drier than IL and IA, and season GDD is the strongest "
            "single separator between the three growers.",
        ],
        size=9.0,
    )
    report.page_break()

    # --- 2. Methods -------------------------------------------------------
    report.heading("2. Comparison levels and methods")
    report.text(
        "The analysis deliberately uses four units of comparison. Each level answers a different "
        "question, and the figures and tables are labelled by level so results are not mixed.",
        space_after=7,
    )
    report.table(
        [
            ["Level", "Unit of analysis", "Question it answers", "Reported evidence"],
            ["Field", "One boundary (n = 30)", "How large and regular are the fields?", "Medians, distributions, shape metrics"],
            ["Field-year", "One field in one year (n = 150)", "How stable are crop and weather over time?", "Crop shares, GDD, precipitation, frost"],
            ["Grower", "10 fields", "What is typical for this operation?", "Grower medians and means"],
            ["Across grower", "Fields pooled by grower", "Are the distributions different?", "Kruskal-Wallis, Mann-Whitney, chi-square, Spearman"],
        ],
        [58, 108, 150, 188],
        size=8.2,
    )
    report.subheading("Statistical choices")
    report.bullets(
        [
            "Tests are nonparametric because each grower has only 10 fields: Kruskal-Wallis for "
            "multi-group differences, Mann-Whitney U for pairwise differences, chi-square for "
            "transition counts, and Spearman for correlations.",
            "Effect sizes are reported alongside p-values: epsilon-squared for Kruskal-Wallis, "
            "rank-biserial for Mann-Whitney, Cramer's V for chi-square, and rho for Spearman.",
            "Pairwise boundary tests and weather correlations use Benjamini-Hochberg adjusted "
            "p-values. All p-values are exploratory at this sample size.",
            "Growing degree days use the daily mean of T2M_MAX and T2M_MIN, base 10 C, cap 30 C, "
            "and April 1 to September 30.",
            "Fields that share an identical NASA POWER daily series are grouped into one weather "
            "cell. Weather comparisons are repeated at field and cell level so shared cells remain "
            "visible.",
        ],
    )
    report.callout(
        "Reading this report",
        "Each figure page starts with the question the chart answers, then the chart, then a short "
        "'what it shows' note. The comparison and correlation figures include effect sizes and "
        "adjusted p-values, so the reader does not need the runtime folder to interpret them.",
    )
    report.subheading("Metric definitions")
    report.table(
        [
            ["Metric", "Definition", "Level"],
            ["Field area", "Polygon area in EPSG:5070, reported in acres", "Field"],
            ["Compactness", "Polsby-Popper: 4 pi area / perimeter squared (1 = circle)", "Field"],
            ["Convexity", "Polygon area / convex-hull area (1 = convex)", "Field"],
            ["Season GDD", "Sum of clipped daily mean temperature, base 10 C, cap 30 C, Apr-Sep", "Field-year"],
            ["Heat days", "Days with T2M_MAX at or above 30 C", "Field-year"],
            ["Frost-free days", "Days between last spring and first fall T2M_MIN <= 0 C", "Field-year"],
            ["Dry days", "Days with precipitation below 1 mm", "Field-year"],
        ],
        [78, 338, 88],
        size=7.9,
    )
    report.page_break()

    # --- 3. Boundary ------------------------------------------------------
    report.heading("3. Boundary analysis")
    report.text(
        "Boundary metrics describe field size and shape and are computed once per field (n = 30). "
        "The two distribution figures show the raw spread; the comparison figure later in the "
        "report tests whether the grower differences are large enough to matter.",
        space_after=5,
    )
    report.image(
        figures / "01_field_size_by_grower.png",
        5.6,
        "What it shows",
        f"Box plots with every field overlaid. IA and IL medians are nearly identical "
        f"(600 and 606 acres); NE is about 15% smaller (514 acres). Kruskal-Wallis p = "
        f"{fmt_p(float(area_kw['p_value']))}, epsilon-squared = "
        f"{float(area_kw['effect_size_epsilon_sq']):.2f}. Pairwise tests confirm IA vs IL is not "
        f"distinguishable (BH p = 0.97), while both differ from NE (BH p < 0.001).",
        dpi=150,
    )
    report.subheading("Boundary summary by grower")
    summary_rows = [["Grower", "Median area", "Compactness", "Convexity", "Vertices", "Area CV"]]
    for _, row in boundary_summary.iterrows():
        summary_rows.append(
            [
                row["grower_slug"].replace("-demo-grower", "").upper(),
                f"{row['area_acres_median']:,.0f} ac",
                f"{row['compactness_median']:.2f}",
                f"{row['convexity_median']:.2f}",
                f"{grower_vertices[row['grower_slug']]:,.0f}",
                f"{row['area_acres_cv']:.2f}",
            ]
        )
    report.table(
        summary_rows,
        [62, 90, 94, 88, 78, 74],
        size=8.4,
        align_right={1, 2, 3, 4, 5},
    )
    report.page_break()

    # --- 3b. Shape --------------------------------------------------------
    report.subheading("Field shape versus field size")
    report.text(
        "Shape metrics are computed from the same 30 boundaries. This scatter tests whether the "
        "larger fields are also simpler, and whether the shape differences line up with growers.",
        space_after=2,
    )
    report.image(
        figures / "02_shape_vs_area.png",
        6.0,
        "What it shows",
        "Compactness against area. Field size weakly predicts compactness (Spearman rho = -0.33, "
        "p = 0.08). Compactness itself does not differ by grower (Kruskal-Wallis p = 0.69), but IL "
        "fields carry more boundary vertices and lower convexity, so shape complexity is a "
        "within-IL feature rather than a simple consequence of larger fields.",
        dpi=150,
    )
    report.bullets(
        [
            "IL has a median of 157 vertices per field, against 88 in IA and 102 in NE. Its median "
            "convexity is 0.80, against 0.92 in IA and 0.85 in NE.",
            "NE fields are not only smaller but also more uniform: area CV is 0.06, versus 0.15 in "
            "IA and 0.19 in IL.",
            "None of the shape metrics separates growers after correction. The visible IL shape "
            "difference is real in the sample but not statistically resolvable at n = 10 per group.",
            "Read the scatter as a shape check, not a size effect: points near the dashed median "
            "line are typical, and the IL points spread low without a matching shift in area.",
        ],
        size=8.9,
    )
    report.page_break()

    # --- 4. Crop ----------------------------------------------------------
    report.heading("4. Crop-history analysis")
    report.text(
        "Crop composition is recomputed from CDL pixel counts so each field-year sums to 100%. Raw "
        "CDL classes are collapsed into Corn, Soybeans, Small grains, Forage, Pasture/Grass, "
        "Fallow/Idle, and Other/Non-crop; the dominant table preserves the raw class name.",
        space_after=5,
    )
    report.image(
        figures / "04_crop_composition.png",
        6.9,
        "What it shows",
        "100% stacked bars for every field-year, one panel per grower-year. Corn and soybeans "
        "account for 98.9% of CDL pixels. The remaining classes are thin field-edge slivers, not "
        "whole fields, and year-to-year changes are swaps between corn and soybeans.",
        dpi=150,
    )
    report.subheading("Rotations")
    report.bullets(
        [
            "Continuous corn is concentrated in NE: 3 of 10 fields, versus 1 of 10 in IL and 0 of "
            "10 in IA. The remaining fields alternate corn and soybeans.",
            "Corn-year and soybean-year counts alone do not separate growers (p = 0.11); the signal "
            "is a few continuous-corn fields rather than a shift of every field.",
            "The rotation heatmap on the next page shows the five-year sequence for each field.",
        ],
        size=8.9,
    )
    crop_rows = [["Grower", "Mean corn years", "Mean soybean years", "Mean run (years)", "Continuous corn"]]
    for _, row in crop_summary.sort_values("grower_slug").iterrows():
        crop_rows.append(
            [
                row["grower_slug"].replace("-demo-grower", "").upper(),
                f"{row['mean_corn_years']:.1f}",
                f"{row['mean_soybean_years']:.1f}",
                f"{row['mean_continuous_years']:.1f}",
                f"{int(row['continuous_corn_fields'])} of 10",
            ]
        )
    report.table(
        crop_rows,
        [62, 108, 118, 116, 100],
        size=8.4,
        align_right={1, 2, 3, 4},
    )
    report.page_break()

    report.subheading("Rotation sequences, 2019-2023")
    report.text(
        "The heatmap lines up all 30 fields on the same five-year window, so the rotation pattern "
        "can be read field by field instead of summarized away.",
        space_after=2,
    )
    report.image(
        figures / "05_rotation_heatmap.png",
        5.3,
        "What it shows",
        "Every field's dominant crop group from 2019 to 2023. Rows are fields grouped by grower; "
        "letters are C (corn), S (soybeans), W (small grains), F (forage), P (pasture), I "
        "(fallow), and O (other). NE's continuous-corn blocks and the near-perfect corn-soybean "
        "alternation elsewhere are visible directly.",
        dpi=150,
    )
    report.bullets(
        [
            f"Continuous corn: {continuous_text}. The other fields alternate corn and soybeans.",
            f"Longest continuous run differs by grower (Kruskal-Wallis p = "
            f"{fmt_p(float(crop_cont['p_value']))}, epsilon-squared = "
            f"{float(crop_cont['effect_size_epsilon_sq']):.2f}).",
            f"Transition counts also differ (chi-square p = {fmt_p(float(crop_chi['p_value']))}, "
            f"Cramer's V = {float(crop_chi['effect_size_cramers_v']):.2f}).",
        ],
        size=8.9,
    )
    report.page_break()

    # --- 5. Weather -------------------------------------------------------
    report.heading("5. Weather analysis")
    report.text(
        "Weather metrics describe the growing environment for each field-year. GDD uses the daily "
        "mean of T2M_MAX and T2M_MIN, base 10 C, cap 30 C, and April 1 to September 30. Frost "
        "metrics use T2M_MIN <= 0 C with the last spring frost at day-of-year 213 or earlier.",
        space_after=5,
    )
    report.image(
        figures / "07_gdd_curves.png",
        6.6,
        "What it shows",
        f"Cumulative GDD by grower; thin lines are fields and thick lines are grower-year means. "
        f"NE accumulates the most heat (mean seasonal GDD {growers.loc[growers['state']=='NE','gdd'].iloc[0]:,.0f} "
        f"versus {growers.loc[growers['state']=='IL','gdd'].iloc[0]:,.0f} in IL and "
        f"{growers.loc[growers['state']=='IA','gdd'].iloc[0]:,.0f} in IA). Kruskal-Wallis p = "
        f"{fmt_p(float(gdd_field['p_value']))} at field level (epsilon-squared = "
        f"{float(gdd_field['effect_size_epsilon_sq']):.2f}) and p = {fmt_p(float(gdd_cell['p_value']))} "
        f"at the weather-cell level (epsilon-squared = {float(gdd_cell['effect_size_epsilon_sq']):.2f}).",
        dpi=150,
    )
    report.image(
        figures / "08_monthly_precip.png",
        6.6,
        "What it shows",
        "Five-year mean monthly precipitation per grid cell, with observed min-max whiskers and the "
        "April-September season shaded. IA peaks in June-August; IL carries more rain in spring "
        "and fall; NE is the driest overall (610 mm/year versus 775 in IA and 917 in IL). The wide "
        "whiskers show that interannual variability is large relative to the grower differences.",
        dpi=150,
    )
    report.page_break()

    # --- 6. Comparisons ---------------------------------------------------
    report.heading("6. Comparison and correlation analyses")
    report.text(
        "Every comparison or correlation test has its own figure. The first two translate the "
        "boundary and crop tables into effect-size views; the next two show that weather "
        "differences survive the shared-cell correction and organize into two climate axes.",
        space_after=5,
    )
    report.image(
        figures / "10_boundary_comparison_effects.png",
        6.7,
        "What it shows",
        "Metric by grower-pair heatmap. Color and the top number are the rank-biserial effect; the "
        "second number is the BH-adjusted p-value, and negative means the first grower's fields are "
        "larger. Area is the only boundary metric that separates growers: IA and IL are "
        "indistinguishable, while NE fields are smaller than both. No shape pair survives "
        "correction (smallest p = 0.16).",
        dpi=150,
    )
    report.image(
        figures / "11_crop_comparison_effects.png",
        6.7,
        "What it shows",
        "Left: Kruskal-Wallis epsilon-squared for the four rotation metrics, with significant "
        "effects in orange. Right: grower by transition heatmap of observed counts and standardized "
        "residuals. NE records 16 corn-to-corn transitions against about 7 expected (residual "
        "+3.4), while IA records 1 (-2.3) and IL 4 (-1.1).",
        dpi=150,
    )
    report.page_break()

    report.image(
        figures / "12_weather_comparison_effects.png",
        5.8,
        "What it shows",
        "Dumbbell chart with one row per weather metric. Blue is the field-level Kruskal-Wallis "
        "epsilon-squared; orange is the same test after collapsing fields to distinct NASA POWER "
        "cells. GDD remains the strongest separator (0.75 field, 0.72 cell), and the largest "
        "field-to-cell drop is 0.06 for frost-free days. Shared cells do not explain the gaps.",
        dpi=150,
    )
    report.image(
        figures / "13_weather_correlation_matrix.png",
        5.8,
        "What it shows",
        f"Spearman rho for every pair of seasonal metrics across 150 field-years, with the lower "
        f"triangle masked and BH-adjusted significance stars. The metrics form a heat axis and a "
        f"moisture axis: GDD and heat days rise together (rho = "
        f"{float(positive['rho']):.2f}), while heat days and annual precipitation move oppositely "
        f"(rho = {float(negative['rho']):.2f}). Frost is nearly independent of both; "
        f"{significant} of {len(correlations)} pairs survive correction.",
        dpi=150,
    )
    report.page_break()

    # --- 7. Maps ----------------------------------------------------------
    report.heading("7. Geospatial maps")
    report.text(
        "The maps place the statistical results back on the landscape. The field-layout map on the "
        "scope page shows where the growers are; the two maps here show the 2023 crop snapshot and "
        "the weather-cell geography.",
        space_after=5,
    )
    report.image(
        figures / "06_crop_map_2023.png",
        6.9,
        "What the map shows",
        "Dominant crop group in 2023, one panel per grower. The 2023 CDL class matches the "
        "grower-reported field crop for all 30 fields. IL is corn-heavy (8 of 10 fields), IA is "
        "soybean-heavy (7 of 10), and NE is an even split. This is the final column of the rotation "
        "heatmap, not independent evidence.",
        dpi=150,
    )
    report.image(
        figures / "09_weather_map.png",
        6.9,
        "What the map shows",
        f"Each bubble is a distinct NASA POWER grid cell; bubble size is the number of fields "
        f"sharing it. The 30 fields collapse to {grower_cells.min()}-{grower_cells.max()} cells per "
        f"grower ("
        + ", ".join(
            f"{slug.split('-')[0].upper()} {int(grower_cells.get(slug, 0))}"
            for slug in sorted(grower_cells.index)
        )
        + f"), holding {int(fields_per_cell.min())}-{int(fields_per_cell.max())} fields each. "
        "Effective spatial replication is far below the field count, so cell-level tests are the "
        "conservative read.",
        dpi=150,
    )
    report.page_break()

    # --- 8. Limitations ---------------------------------------------------
    report.heading("8. Limitations, assumptions, and missing data")
    report.bullets(
        [
            "Demo scale. Ten fields per grower is a demonstration, not a survey. P-values are "
            "exploratory and should not be read as population inference.",
            "No outcome linkage. The EDA contains no yield, management, economic, or treatment "
            "data, so it cannot attribute causes to the differences it finds.",
            "Mismatched windows. CDL covers 2019-2023 and weather covers 2021-2025. There is no "
            "paired crop-year weather analysis and no yield model.",
            "CDL edge mixing. Pixel shares include field-edge mixing; the non-crop share is not a "
            "land-use estimate. Only the dominant class is used for rotation.",
            "Simple agronomic models. GDD is a daily-average formula, not a crop-specific model. "
            "Frost uses a fixed 0 C threshold and day-of-year split.",
            "Shared weather cells. Fields in one NASA POWER cell share a daily series, so "
            "field-level weather n overstates independent replication. Cell-level results are the "
            "conservative number.",
            "Demo identity. Grower and farm names are demo labels; counties are for orientation, "
            "not a claim about commercial operations.",
            "Missing layers. Soil, terrain, imagery, and management records are not part of this "
            "EDA. The analysis is intentionally limited to boundaries, CDL crop history, and "
            "weather.",
        ],
        size=9.0,
    )
    report.y -= 4
    report.callout(
        "Soil scope",
        "Soil analysis was not required and was not a focus of this EDA. No soil layer was read, "
        "joined, or modeled, and no soil result appears in the tables or figures. The workflow "
        "focuses on field boundaries, crop history, and weather.",
    )
    report.text(
        "Assumption summary: geometry is measured in an equal-area projection (EPSG:5070); crop "
        "composition uses pixel counts rather than rounded percentages; weather cells are inferred "
        "from identical daily series; and all multi-group tests treat fields as independent except "
        "where the cell-level rerun explicitly corrects that.",
        size=8.8,
        color=MUTED,
        leading=1.42,
    )
    report.callout(
        "How this report was produced",
        "The PDF is assembled from a completed field-eda run: manifest.json, 15 CSV tables, and 13 "
        "PNG figures. The reusable workflow lives at my-farm-advisor/eda/field-eda/. The one-time "
        "builder and rebuild instructions sit in reports/assignment-2-field-eda/. No runtime folder "
        "is needed to read this report.",
    )
    report.subheading("What this EDA supports")
    report.bullets(
        [
            "A reproducible baseline for the three demo farms: boundary, crop-history, and weather "
            "distributions that later analyses can reuse or extend.",
            "A clear split between what the sample resolves (field size, GDD, transitions) and what "
            "it does not (shape metrics, frost-free days).",
            "A starting point for deeper work: yield and management linkage, more fields per "
            "grower, and aligned crop and weather windows.",
        ],
        size=8.9,
    )
    report.page_break()

    # --- 9. Appendix ------------------------------------------------------
    report.heading("9. Artifact inventory and headline statistics")
    report.subheading("Headline tests")
    report.table(
        [
            ["Category", "Test", "p-value", "Effect size"],
            ["Boundary: area", "Kruskal-Wallis", fmt_p(float(area_kw["p_value"])), f"epsilon-squared = {float(area_kw['effect_size_epsilon_sq']):.2f}"],
            ["Boundary: compactness", "Kruskal-Wallis", fmt_p(float(compact_kw["p_value"])), f"epsilon-squared = {float(compact_kw['effect_size_epsilon_sq']):.2f}"],
            ["Boundary: convexity", "Kruskal-Wallis", fmt_p(float(convex_kw["p_value"])), f"epsilon-squared = {float(convex_kw['effect_size_epsilon_sq']):.2f}"],
            ["Crop: longest continuous run", "Kruskal-Wallis", fmt_p(float(crop_cont["p_value"])), f"epsilon-squared = {float(crop_cont['effect_size_epsilon_sq']):.2f}"],
            ["Crop: transitions", "Chi-square", fmt_p(float(crop_chi["p_value"])), f"Cramer's V = {float(crop_chi['effect_size_cramers_v']):.2f}"],
            ["Weather: GDD, field", "Kruskal-Wallis", fmt_p(float(gdd_field["p_value"])), f"epsilon-squared = {float(gdd_field['effect_size_epsilon_sq']):.2f}"],
            ["Weather: GDD, cell", "Kruskal-Wallis", fmt_p(float(gdd_cell["p_value"])), f"epsilon-squared = {float(gdd_cell['effect_size_epsilon_sq']):.2f}"],
            ["Weather: annual precip, field", "Kruskal-Wallis", fmt_p(float(annual_field["p_value"])), f"epsilon-squared = {float(annual_field['effect_size_epsilon_sq']):.2f}"],
            ["Weather: heat days, field", "Kruskal-Wallis", fmt_p(float(heat_field["p_value"])), f"epsilon-squared = {float(heat_field['effect_size_epsilon_sq']):.2f}"],
            ["Weather: frost-free days, field", "Kruskal-Wallis", fmt_p(float(frost_field["p_value"])), f"epsilon-squared = {float(frost_field['effect_size_epsilon_sq']):.2f}"],
            ["Weather: growing precip, field", "Kruskal-Wallis", fmt_p(float(growing_field["p_value"])), f"epsilon-squared = {float(growing_field['effect_size_epsilon_sq']):.2f}"],
        ],
        [150, 92, 78, 184],
        size=8.0,
        align_right={2},
    )

    report.subheading("Artifacts in this run")
    report.table(
        [
            ["Group", "Tables", "Figures"],
            ["Boundary", "field_boundary_metrics; boundary_comparison; boundary_grower_summary", "01, 02, 03, 10"],
            ["Crop history", "crop_composition; crop_dominant; crop_rotation_summary; crop_transitions; crop_comparison; crop_grower_summary", "04, 05, 06, 11"],
            ["Weather", "weather_seasonal_metrics; weather_comparison; weather_grower_summary; weather_correlations; weather_cells", "07, 08, 09, 12, 13"],
            ["Field profile", "field_profile", "-"],
            ["Total", "15 tables", "13 figures"],
        ],
        [62, 286, 156],
        size=7.8,
    )

    report.subheading("Provenance")
    report.bullets(
        [
            f"Reusable subskill: my-farm-advisor/eda/field-eda/ (not modified by this report).",
            f"Source run: $DATA_PIPELINE_DATA_ROOT/data-pipeline/eda/field-eda",
            f"Manifest generated: {generated_at}; report built {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}.",
            "Runtime tables, figures, and the manifest stay outside Git. This PDF and its notes are the "
            "committed handoff.",
        ],
        size=8.6,
    )

    report.finish()
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf.write(
        output,
        {
            "Title": "Field-Level EDA of Three Demo Growers - Assignment 2",
            "Author": "My Farm Advisor",
            "Subject": "Field boundaries, CDL crop history, and NASA POWER weather EDA",
            "Creator": "reports/assignment-2-field-eda/build_report.py",
            "CreationDate": datetime.now(UTC).strftime("D:%Y%m%d%H%M%SZ"),
        },
    )
    size_kb = output.stat().st_size / 1024
    print(f"Wrote {output} ({size_kb:.0f} KB, {len(pdf.pages)} pages)")


if __name__ == "__main__":
    main()
