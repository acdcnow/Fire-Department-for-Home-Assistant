"""Sensor platform for the Fire Department Austria integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import provider
from .const import KIND_HISTORY, KIND_ICONS, KIND_ACTIVE
from .coordinator import FireDepartmentCoordinator
from .entity import FireDepartmentEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one sensor per configured source."""
    coordinator: FireDepartmentCoordinator = entry.runtime_data
    entities = [
        FireDepartmentSensor(coordinator, entry, source) for source in coordinator.sources
    ]
    if entities:
        async_add_entities(entities)


class FireDepartmentSensor(FireDepartmentEntity, SensorEntity):
    """Number of rows of one source, with the rows themselves as attributes."""

    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: FireDepartmentCoordinator,
        entry: ConfigEntry,
        source: dict[str, Any],
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry, source)
        self._attr_unique_id = f"{entry.entry_id}_{source['id']}"
        self._attr_icon = KIND_ICONS.get(source["kind"], "mdi:fire-station")
        if source["id"].startswith("custom_"):
            self._attr_name = source.get("label") or "Custom source"
        else:
            self._attr_translation_key = source["kind"]

    @property
    def native_value(self) -> int:
        """Number of incidents / brigades currently reported."""
        return self.row_count

    @property
    def available(self) -> bool:
        """Unavailable when this source could not be read at all."""
        return super().available and self._source_id in (self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the parsed rows plus aggregates for dashboards."""
        attributes = self.source_attributes
        attributes.update(self.rows_attributes)
        if self._source["kind"] == KIND_HISTORY:
            durations = [
                row["duration_minutes"] for row in self.rows if row.get("duration_minutes")
            ]
            if durations:
                attributes["average_duration_minutes"] = round(sum(durations) / len(durations))
                attributes["average_duration"] = provider.humanize_duration(
                    attributes["average_duration_minutes"]
                )
        if self._source["kind"] == KIND_ACTIVE:
            attributes["longest_running"] = _longest_running(self.rows)
        return attributes


def _longest_running(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Oldest still running incident."""
    running = [row for row in rows if row.get("started") or row.get("age")]
    if not running:
        return None
    candidates = [row for row in rows if row.get("started")]
    if candidates:
        return min(candidates, key=lambda row: row["started"])
    return running[0]
