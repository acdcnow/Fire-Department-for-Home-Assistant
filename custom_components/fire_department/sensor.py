"""Platform for sensor integration."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    KEY_ACTIVE_OPS,
    KEY_COMPLETED,
    KEY_DEPLOYED_FF,
    TYPE_DEPARTMENTS,
    TYPE_INCIDENTS,
)
from .coordinator import FireDeptCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup sensor platform."""
    coordinator: FireDeptCoordinator = hass.data[DOMAIN][entry.entry_id]
    pages = coordinator.pages

    if not pages:
        return

    async_add_entities(
        [
            FireDeptSensor(coordinator, entry, page, idx)
            for idx, page in enumerate(pages)
        ]
    )


class FireDeptSensor(SensorEntity):
    """Dynamic Sensor."""
    _attr_has_entity_name = True 

    def __init__(self, coordinator, entry, page_config, page_index):
        self.coordinator = coordinator
        self._entry = entry
        self._page = page_config
        self._idx = page_index
        
        t_key = page_config.get("name")
        self._attr_translation_key = t_key 
        
        if t_key not in [KEY_ACTIVE_OPS, KEY_DEPLOYED_FF, KEY_COMPLETED]:
             if page_config.get("name"):
                 self._attr_name = page_config["name"]
                 self._attr_translation_key = None 

        self._attr_unique_id = f"{entry.entry_id}_{page_index}"
        self._attr_icon = "mdi:fire-truck" if page_config["type"] == TYPE_INCIDENTS else "mdi:shield-account"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="NÖ Landeswarnzentrale",
            model="WASTL Scraper",
        )

    @property
    def native_value(self):
        data = self.coordinator.data.get(self._idx, [])
        return len(data)

    @property
    def extra_state_attributes(self):
        return {
            "data_list": self.coordinator.data.get(self._idx, []),
            "url": self._page["url"]
        }
