"""Map markers for the currently active operations.

Every active operation becomes a ``geo_location`` entity, which is exactly what
the built-in Home Assistant map card picks up through
``geo_location_sources``. The marker position is the centre of the municipality
the operation was reported in (see ``geocoding.py``), its name is
"<Einsatzart> · <Gemeinde>" and its state is the distance from home in metres.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify
from homeassistant.util.location import distance

from .const import (
    DOMAIN,
    ROW_CENTER,
    ROW_DATE,
    ROW_KIND,
    ROW_PLACE,
    ROW_TIME,
    SOURCE,
)
from .coordinator import FireDeptCoordinator
from .geocoding import MunicipalityGeocoder

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the map markers of one config entry."""
    coordinator: FireDeptCoordinator = hass.data[DOMAIN][entry.entry_id]
    manager = _MarkerManager(hass, entry, coordinator, async_add_entities)

    await manager.async_sync()
    entry.async_on_unload(coordinator.async_add_listener(manager.handle_coordinator_update))


class _MarkerManager:
    """Keeps the markers in sync with the active operations."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: FireDeptCoordinator,
        async_add_entities: AddConfigEntryEntitiesCallback,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.async_add_entities = async_add_entities
        self.geocoder = MunicipalityGeocoder(hass)
        self.entities: dict[str, FireDeptOperationMarker] = {}
        self._busy = False

    @callback
    def handle_coordinator_update(self) -> None:
        """React to new scraped data."""
        self.hass.async_create_task(self.async_sync(), "fire_department map markers")

    async def async_sync(self) -> None:
        """Create, keep or remove markers - one sync at a time."""
        if self._busy:
            return
        self._busy = True
        try:
            await self._async_sync()
        finally:
            self._busy = False

    async def _async_sync(self) -> None:
        wanted: dict[str, list[str]] = {}
        for row in self.coordinator.active_operations():
            key = _marker_key(row, wanted)
            wanted[key] = row

        # Operations that are over disappear from the map.
        for key, entity in list(self.entities.items()):
            if key not in wanted:
                self.entities.pop(key)
                await entity.async_remove()

        new_entities: list[FireDeptOperationMarker] = []
        for key, row in wanted.items():
            if key in self.entities:
                continue
            coords = await self.geocoder.async_lookup(row[ROW_PLACE])
            if coords is None:
                continue
            entity = FireDeptOperationMarker(self.entry, key, row, coords)
            self.entities[key] = entity
            new_entities.append(entity)

        if new_entities:
            self.async_add_entities(new_entities)


def _marker_key(row: list[str], taken: dict[str, list[str]]) -> str:
    """Build a unique but stable key for one operation."""
    key = slugify(f"{row[ROW_PLACE]}_{row[ROW_KIND]}_{row[ROW_DATE]}_{row[ROW_TIME]}")
    key = key or "einsatz"
    if key in taken:
        counter = 2
        while f"{key}_{counter}" in taken:
            counter += 1
        key = f"{key}_{counter}"
    return key


class FireDeptOperationMarker(GeolocationEvent):
    """One marker for one active operation."""

    _attr_should_poll = False
    _attr_source = SOURCE

    def __init__(
        self,
        entry: ConfigEntry,
        key: str,
        row: list[str],
        coords: tuple[float, float],
    ) -> None:
        self._entry = entry
        self._row = row
        self._attr_unique_id = f"{entry.entry_id}_geo_{key}"
        self._attr_name = f"{row[ROW_KIND]} · {row[ROW_PLACE]}"
        self._attr_latitude = coords[0]
        self._attr_longitude = coords[1]

    async def async_added_to_hass(self) -> None:
        """Calculate the distance from home once the entity knows its hass."""
        await super().async_added_to_hass()
        home_lat = self.hass.config.latitude
        home_lon = self.hass.config.longitude
        if home_lat is not None and home_lon is not None:
            self._attr_distance = distance(
                self._attr_latitude,
                self._attr_longitude,
                home_lat,
                home_lon,
            )
            self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Group the markers with the sensors of the same entry."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="NÖ Landeswarnzentrale",
            model="WASTL Scraper",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the row details for dashboards and automations."""
        return {
            "gemeinde": self._row[ROW_PLACE],
            "einsatzart": self._row[ROW_KIND],
            "alarmzentrale": self._row[ROW_CENTER],
            "datum": self._row[ROW_DATE],
            "zeit": self._row[ROW_TIME],
            "quelle": "WASTL / NÖ Landeswarnzentrale",
        }
