"""Map markers for the missions that are running right now.

Every running mission becomes a ``geo_location`` entity, which is exactly what
the built-in map card picks up through ``geo_location_sources``.  The marker
sits in the centre of the municipality the mission was reported in (see
:mod:`geocoding`), its name is ``<keyword> · <municipality>`` and its state is
the distance from home in metres.

Markers appear and disappear with the missions, so the map always shows the
current situation.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.location import distance

from .const import (
    CONF_MAP_MARKERS,
    DEFAULT_MAP_MARKERS,
    KIND_ACTIVE,
    SOURCE_MAP_MARKERS,
)
from .coordinator import FireDepartmentCoordinator
from .entity import FireDepartmentEntity
from .geocoding import MunicipalityGeocoder

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the mission markers of all running mission sources."""
    if not entry.options.get(CONF_MAP_MARKERS, DEFAULT_MAP_MARKERS):
        _LOGGER.debug("Map markers are switched off for %s", entry.title)
        return

    coordinator: FireDepartmentCoordinator = entry.runtime_data
    manager = MissionMarkerManager(hass, entry, coordinator, async_add_entities)
    await manager.async_sync()
    entry.async_on_unload(coordinator.async_add_listener(manager.handle_coordinator_update))
    _LOGGER.debug("Map markers for %s ready (%s missions)", entry.title, len(manager.entities))


class MissionMarkerManager:
    """Keeps one marker per running mission in sync with the coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: FireDepartmentCoordinator,
        async_add_entities: AddEntitiesCallback,
        geocoder: MunicipalityGeocoder | None = None,
    ) -> None:
        """Initialise the manager."""
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.async_add_entities = async_add_entities
        self.geocoder = geocoder or MunicipalityGeocoder(hass)
        self.entities: dict[str, FireDepartmentMissionMarker] = {}
        self._busy = False

    @property
    def active_sources(self) -> list[dict[str, Any]]:
        """Sources that report running missions."""
        return [
            source
            for source in self.coordinator.sources
            if source.get("kind") == KIND_ACTIVE
        ]

    @callback
    def handle_coordinator_update(self) -> None:
        """React to freshly scraped data."""
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
        wanted: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        for source in self.active_sources:
            rows = (self.coordinator.data or {}).get(source["id"]) or []
            for row in rows:
                if not row.get("id") or row.get("running") is False:
                    continue
                wanted[f"{source['id']}:{row['id']}"] = (source, row)

        # missions that are over disappear from the map
        for key, entity in list(self.entities.items()):
            if key not in wanted:
                self.entities.pop(key)
                await entity.async_remove()

        new_entities: list[FireDepartmentMissionMarker] = []
        for key, (source, row) in wanted.items():
            if key in self.entities:
                continue
            coords = await self.geocoder.async_lookup(
                row.get("municipality"), source.get("region")
            )
            if coords is None:
                _LOGGER.debug(
                    "No coordinates for %r (%s)",
                    row.get("municipality"),
                    source.get("region"),
                )
                continue
            entity = FireDepartmentMissionMarker(
                self.coordinator, self.entry, source, row, coords
            )
            self.entities[key] = entity
            new_entities.append(entity)

        if new_entities:
            self.async_add_entities(new_entities)


class FireDepartmentMissionMarker(FireDepartmentEntity, GeolocationEvent):
    """One map marker for one running mission."""

    _attr_should_poll = False
    _attr_source = SOURCE_MAP_MARKERS

    def __init__(
        self,
        coordinator: FireDepartmentCoordinator,
        entry: ConfigEntry,
        source: dict[str, Any],
        row: dict[str, Any],
        coords: tuple[float, float],
    ) -> None:
        """Initialise the marker from the mission row it represents."""
        super().__init__(coordinator, entry, source)
        self._mission_id = row["id"]
        self._snapshot = row
        self._attr_unique_id = f"{entry.entry_id}_geo_{source['id']}_{row['id']}"
        self._attr_latitude = coords[0]
        self._attr_longitude = coords[1]
        label = row.get("keyword") or row.get("type") or "Mission"
        place = row.get("municipality") or source.get("label") or "unknown"
        self._attr_name = f"{label} · {place}"

    # ------------------------------------------------------------------ #
    # data access
    # ------------------------------------------------------------------ #
    @property
    def mission(self) -> dict[str, Any]:
        """The current row of this mission (falls back to the last known one)."""
        for row in self.rows:
            if row.get("id") == self._mission_id:
                self._snapshot = row
                return row
        return self._snapshot

    async def async_added_to_hass(self) -> None:
        """Add the distance from home once the entity knows its hass."""
        await super().async_added_to_hass()
        config = getattr(self.hass, "config", None)
        if config is None or config.latitude is None or config.longitude is None:
            return
        self._attr_distance = distance(
            self._attr_latitude, self._attr_longitude, config.latitude, config.longitude
        )
        self.async_write_ha_state()

    # ------------------------------------------------------------------ #
    # attributes
    # ------------------------------------------------------------------ #
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the mission plus the source it came from."""
        mission = self.mission
        attributes: dict[str, Any] = {
            "mission_id": self._mission_id,
            "municipality": mission.get("municipality"),
            "district": mission.get("district"),
            "district_code": mission.get("district_code"),
            "type": mission.get("type"),
            "keyword": mission.get("keyword"),
            "category": mission.get("category"),
            "severity": mission.get("severity"),
            "color": mission.get("color"),
            "started": mission.get("started"),
            "age": mission.get("age"),
            "running": mission.get("running"),
            "unit_count": mission.get("unit_count"),
        }
        attributes.update(self.source_attributes)
        return {key: value for key, value in attributes.items() if value is not None}
