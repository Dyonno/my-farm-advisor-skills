"""Reusable field-level EDA for My Farm Advisor.

The modules are also importable as top-level modules because the data-pipeline
adds this ``src`` directory to ``sys.path`` via ``ensure_skill_path``.

Example:
    >>> import field_eda
    >>> manifest = field_eda.run_eda(farms, field_eda.EdaParams(output_dir=...))
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from boundary_metrics import compute_metrics  # noqa: E402,F401
from crop_history import (  # noqa: E402,F401
    classify_code,
    dominant_crops,
    normalize_composition,
)
from field_eda import EdaParams, FarmData, run_eda  # noqa: E402,F401
from weather_metrics import assign_weather_cells, prepare_daily  # noqa: E402,F401

__all__ = [
    "EdaParams",
    "FarmData",
    "assign_weather_cells",
    "classify_code",
    "compute_metrics",
    "dominant_crops",
    "normalize_composition",
    "prepare_daily",
    "run_eda",
]
