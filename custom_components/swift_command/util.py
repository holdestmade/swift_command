"""Utility functions for the Swift Command integration."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

_LOGGER = logging.getLogger(__name__)

# Words rendered fully uppercase in friendly names
_ACRONYMS = {"psu", "enum", "ac", "dc", "id", "gps", "cp", "ec630", "atc"}

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_BOUNDARY_RE = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")


def prettify_key(key: str) -> str:
    """Turn an API key like 'batteryCurrentDirection' into 'Battery Current Direction'.

    Splits underscores and camelCase boundaries into words, title-cases each
    word, and uppercases known acronyms (e.g. 'electricSettingEnum' becomes
    'Electric Setting ENUM', 'psuSoftwareNumber' becomes 'PSU Software Number').
    """
    spaced = key.replace("_", " ")
    spaced = _CAMEL_BOUNDARY_RE.sub(" ", spaced)
    spaced = _ACRONYM_BOUNDARY_RE.sub(" ", spaced)
    return " ".join(
        word.upper() if word.lower() in _ACRONYMS else word.title()
        for word in spaced.split()
    )


def get_nested_value(data: dict | list | None, keys: Iterable[Any]) -> Any | None:
    """Safely get a nested value from a dict/list by walking `keys`."""
    current: Any = data
    for key_idx, key in enumerate(keys):
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and isinstance(key, int) and 0 <= key < len(current):
            current = current[key]
        else:
            _LOGGER.debug(
                "Path not found in data: missing key '%s' at level %d for full path %s",
                key,
                key_idx,
                "->".join(map(str, keys)),
            )
            return None
    return current


# The Swift Command backend reports fixTime in UK local time (GMT/BST)
_FIX_TIME_TZ = ZoneInfo("Europe/London")


def parse_fix_time(value: Any) -> datetime | None:
    """Parse lastPosition.fixTime (e.g. 20260716080127, YYYYMMDDHHMMSS, UK local time)."""
    if value is None:
        return None
    s = str(value).strip()
    if len(s) != 14 or not s.isdigit():
        return None
    try:
        return datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=_FIX_TIME_TZ)
    except ValueError:
        return None


def calculate_power_watts(
    amps: float | None,
    measured_volts: float | None,
    default_volts: float,
    *,
    absolute: bool = True,
) -> float | None:
    """Calculate power (W) given current and a measured-or-default voltage.

    - If `measured_volts` is not None, it is used; otherwise `default_volts`.
    - If `amps` is None, returns None.
    - When `absolute=True`, the absolute value of current is used (useful for battery charge/discharge).
    """
    if amps is None:
        return None
    volts = measured_volts if measured_volts is not None else default_volts
    current = abs(amps) if absolute else amps
    return round(current * volts, 1)
