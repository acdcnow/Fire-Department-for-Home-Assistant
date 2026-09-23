"""Shared data coordinator for the Fire Department integration.

The coordinator is created once per config entry in ``__init__.py`` so that the
``sensor`` and the ``geo_location`` platform work on the very same scrape
instead of fetching every page twice.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any

from bs4 import BeautifulSoup

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, KEY_ACTIVE_OPS, TYPE_DEPARTMENTS, TYPE_INCIDENTS

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15


class FireDeptCoordinator(DataUpdateCoordinator[dict[int, list[list[str]]]]):
    """Fetch and parse all pages of a config entry."""

    def __init__(
        self, hass: HomeAssistant, pages: list[dict[str, Any]], interval_minutes: int
    ) -> None:
        """Initialise the coordinator.

        The shared Home Assistant aiohttp session is used on purpose: a session
        created here would have to be closed again on every reload.
        """
        self.session = async_get_clientsession(hass)
        self.pages = pages
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval_minutes),
        )

    @property
    def active_operations_page(self) -> int | None:
        """Return the index of the page holding the active operations."""
        for idx, page in enumerate(self.pages):
            if page.get("name") == KEY_ACTIVE_OPS:
                return idx
        # Fall back to the first incidents page for custom configured entries.
        for idx, page in enumerate(self.pages):
            if page.get("type") == TYPE_INCIDENTS:
                return idx
        return None

    def active_operations(self) -> list[list[str]]:
        """Return the parsed rows of the active operations page."""
        idx = self.active_operations_page
        if idx is None:
            return []
        return (self.data or {}).get(idx) or []

    async def _async_update_data(self) -> dict[int, list[list[str]]]:
        data: dict[int, list[list[str]]] = {}
        for idx, page in enumerate(self.pages):
            data[idx] = await self.fetch_and_parse(page["url"], page["type"])
        return data

    async def fetch_and_parse(self, url: str, p_type: str) -> list[list[str]]:
        """Fetch a page and parse its table rows."""
        data_list: list[list[str]] = []
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self.session.get(url) as response:
                    text = await response.text(encoding="ISO-8859-1")

            soup = BeautifulSoup(text, "html.parser")
            rows = soup.find_all("tr")

            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    raw_data = [ele.text.strip() for ele in cols]

                    # Skip Headers
                    if not raw_data or "Zeit" in str(raw_data) or "Feuerwehr" in str(raw_data):
                        continue

                    formatted_row = self.process_row_smart(raw_data, p_type)
                    if formatted_row:
                        data_list.append(formatted_row)

            return data_list
        except Exception as err:  # noqa: BLE001 - keep one bad page from breaking all
            _LOGGER.error("Error parsing %s: %s", url, err)
            return []

    def process_row_smart(self, row: list[str], p_type: str) -> list[str] | None:
        """Smartly detect columns based on Time format."""
        try:
            # 1. Find the index of the Time column (contains :)
            time_idx = -1
            for i, col in enumerate(row):
                if ":" in col or "std" in col.lower():  # Matches "12:00" or "< 1 std."
                    time_idx = i
                    break

            if time_idx == -1:
                return None  # No time found, invalid row

            # 2. Extract relative to Time
            raw_time = row[time_idx]
            incident_type = row[time_idx - 1] if time_idx >= 1 else "-"

            district = "-"
            location = "-"

            if p_type == TYPE_INCIDENTS:
                # Layout: [Hidden] [District] [Location] [Type] [Time]
                # If Time is at index 4: Type=3, Loc=2, Dist=1
                location = row[time_idx - 2] if time_idx >= 2 else "-"
                district = self.clean_text(row[time_idx - 3]) if time_idx >= 3 else "-"

            elif p_type == TYPE_DEPARTMENTS:
                # Layout: [Hidden] [Department] [Type] [Time]
                # If Time is at index 3: Type=2, Dept=1
                district = self.clean_text(row[time_idx - 2]) if time_idx >= 2 else "-"
                location = "-"

            date_str, time_str = self.split_datetime(raw_time)

            return [date_str, time_str, district, location, incident_type]

        except Exception:  # noqa: BLE001
            return None

    def clean_text(self, text: str) -> str:
        """Remove leading numbers."""
        return re.sub(r"^\d+\s*", "", text)

    def split_datetime(self, raw_str: str) -> tuple[str, str]:
        """Split Date and Time."""
        match = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*(.*)", raw_str)
        if match:
            return match.group(1), match.group(2)
        return "-", raw_str
