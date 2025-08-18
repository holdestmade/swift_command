"""Utility functions for the Swift Command integration."""
from __future__ import annotations

import logging
from typing import Iterable, Any

_LOGGER = logging.getLogger(__name__)


def _get_nested_value(data: dict | list | None, keys: Iterable[Any]) -> Any | None:
    """Safely get a nested value from a dict/list by walking `keys`.

    Private helper; use the public alias `get_nested_value` for imports.
    """
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


# Public alias (import this everywhere)
get_nested_value = _get_nested_value


def calculate_power_watts(
    amps: float | None,
    measured_volts: float | None,
    default_volts: float,
    *,
    absolute: bool = True,
) -> float | None:
    """Calculate power (W) given current and a measured-or-default voltage.

    - If `measured_volts` is truthy, it is used; otherwise `default_volts`.
    - If `amps` is None, returns None.
    - When `absolute=True`, the absolute value of current is used (useful for battery charge/discharge).
    """
    if amps is None:
        return None
    v = measured_volts if measured_volts is not None else default_volts
    a = abs(amps) if absolute else amps
    try:
        return round(a * v, 1)
    except Exception:  # noqa: BLE001
        return None
