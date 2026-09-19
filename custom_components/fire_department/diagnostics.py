"""Diagnostics support for the Fire Department Austria integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import FireDepartmentCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: FireDepartmentCoordinator = entry.runtime_data
    data = coordinator.data or {}
    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "options": dict(entry.options),
        },
        "sources": [dict(source) for source in coordinator.sources],
        "update_interval_minutes": (
            coordinator.update_interval.total_seconds() / 60 if coordinator.update_interval else None
        ),
        "color_scheme": coordinator.color_scheme,
        "filter_categories": coordinator.categories,
        "max_items": coordinator.max_items,
        "last_update_success": coordinator.last_update_success,
        "failed_sources": sorted(coordinator.failed_sources),
        "last_error": coordinator.last_error,
        "fetched_at": coordinator.fetched_at.isoformat() if coordinator.fetched_at else None,
        "data": {
            source_id: {"count": len(rows), "first_rows": rows[:2]}
            for source_id, rows in data.items()
        },
    }
