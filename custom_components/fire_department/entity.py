"""Shared entity helpers for the Fire Department Austria integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import provider
from .const import CONF_REGION, DOMAIN, REGION_LABELS
from .coordinator import FireDepartmentCoordinator


class FireDepartmentEntity(CoordinatorEntity[FireDepartmentCoordinator]):
    """Base class for all entities of one source."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FireDepartmentCoordinator,
        entry: ConfigEntry,
        source: dict[str, Any],
    ) -> None:
        """Initialise the entity for one source."""
        super().__init__(coordinator)
        self._entry = entry
        self._source = source
        self._source_id: str = source["id"]

    # ------------------------------------------------------------------ #
    # data access
    # ------------------------------------------------------------------ #
    @property
    def rows(self) -> list[dict[str, Any]]:
        """Rows of this source (newest first)."""
        if not self.coordinator.data:
            return []
        return self.coordinator.data.get(self._source_id) or []

    @property
    def row_count(self) -> int:
        """Number of rows reported by the source."""
        return len(self.rows)

    @property
    def available(self) -> bool:
        """Entity is available as long as its own source could be read."""
        return super().available and self._source_id not in self.coordinator.failed_sources

    # ------------------------------------------------------------------ #
    # device + attributes
    # ------------------------------------------------------------------ #
    @property
    def device_info(self) -> DeviceInfo:
        """Group all sources of a config entry into one device."""
        region = self._entry.options.get(CONF_REGION, "custom")
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Fire Department Austria",
            model=REGION_LABELS.get(region, "Custom source"),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=self._source.get("url"),
        )

    @property
    def source_attributes(self) -> dict[str, Any]:
        """Attributes describing the source itself."""
        return {
            "source_id": self._source_id,
            "source_url": self._source.get("url"),
            "source_parser": self._source.get("parser"),
            "source_window": self._source.get("window"),
            "source_kind": self._source.get("kind"),
            "source_region": self._source.get("region"),
            "source_label": self._source.get("label"),
            "fetched_at": (
                self.coordinator.fetched_at.isoformat() if self.coordinator.fetched_at else None
            ),
            "last_error": self.coordinator.last_error,
        }

    @property
    def rows_attributes(self) -> dict[str, Any]:
        """Attribute block shared by all row based entities."""
        rows = self.rows
        limit = self.coordinator.max_items
        shown = rows[:limit] if limit else []
        summary = provider.summarize(rows)
        return {
            "count": len(rows),
            "incidents": shown,
            "truncated": len(shown) < len(rows),
            "max_items": limit,
            "latest_incident": rows[0] if rows else None,
            "by_category": summary["by_category"],
            "by_district": summary["by_district"],
            "by_keyword": summary["by_keyword"],
            "brigades": summary["by_brigade"],
            "filter_categories": self.coordinator.categories,
            "color_scheme": self.coordinator.color_scheme,
            "color_legend": provider.color_legend(self.coordinator.color_scheme),
        }
