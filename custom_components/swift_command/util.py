"""Utility functions for the Swift Command integration."""
from __future__ import annotations

import logging
from typing import Any, Iterable

_LOGGER = logging.getLogger(__name__)


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
