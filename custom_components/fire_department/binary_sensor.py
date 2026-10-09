"""Binary sensor platform for the Fire Department Austria integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KIND_ACTIVE
from .coordinator import FireDepartmentCoordinator
from .entity import FireDepartmentEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one "missions running" binary sensor per active source."""
    coordinator: FireDepartmentCoordinator = entry.runtime_data
    entities = [
        FireDepartmentActiveBinarySensor(coordinator, entry, source)
        for source in coordinator.sources
        if source["kind"] == KIND_ACTIVE
    ]
    if entities:
        async_add_entities(entities)


class FireDepartmentActiveBinarySensor(FireDepartmentEntity, BinarySensorEntity):
    """On while at least one mission is running - handy for automations."""

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_icon = "mdi:fire-alert"

    def __init__(
        self,
        coordinator: FireDepartmentCoordinator,
        entry: ConfigEntry,
        source: dict[str, Any],
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, entry, source)
        self._attr_unique_id = f"{entry.entry_id}_{source['id']}_active"
        if source["id"].startswith("custom_"):
            self._attr_name = f"{source.get('label') or 'Custom source'} active"
        else:
            self._attr_translation_key = "active_operations"

    @property
    def is_on(self) -> bool:
        """True while the source reports at least one running mission."""
        return self.row_count > 0

    @property
    def available(self) -> bool:
        """Unavailable when this source could not be read at all."""
        return super().available and self._source_id in (self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Counts and the newest mission."""
        rows = self.rows
        summary = {
            "count": len(rows),
            "by_category": {},
        }
        for row in rows:
            category = row.get("category")
            if category:
                summary["by_category"][category] = summary["by_category"].get(category, 0) + 1
        return {
            **summary,
            "latest_incident": rows[0] if rows else None,
            **self.source_attributes,
        }
