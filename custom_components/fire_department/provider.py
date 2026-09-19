"""Source adapters and normalisation for the Fire Department integration.

This module is intentionally free of any Home Assistant imports so that it can
be unit tested with a plain Python interpreter (see ``tests/``).

Every source is parsed into a list of *incident* dictionaries with a stable
schema.  Keys without a value are omitted to keep the state attributes small.

==========================  ==================================================
id                          stable identifier (source + date + place + type)
source                      source id from ``const.SOURCES``
source_url                  URL the row was read from
kind                        ``active_operations`` / ``deployed_fire_brigade``
                            / ``completed_missions``
window                      ``live`` / ``24h`` / ``month`` / ``custom``
date                        ``DD.MM.YYYY`` as published by the source
started                     ISO 8601 timestamp with timezone (often missing)
ended                       ISO 8601 timestamp (only if the source knows it)
duration_minutes            integer, only when started *and* ended are known
time                        ``HH:MM`` as published
age                         relative age text from the source (``< 1 std.``)
station                     alerting control centre (WASTL only)
municipality                town / municipality (Gemeinde)
district                    full district name (Bezirk) when resolvable
district_code               short district code (``BR``, ``LB``, ...)
type                        full alert / incident text (Einsatzart)
keyword                     normalised alarm keyword (``B1``, ``T03V``, ``SOF1``)
category                    fire / technical / hazardous / exercise / special /
                            other
level                       numeric alarm level, only for one digit keywords
severity                    derived: high / medium / low / info
color                       colour for the row (depends on the colour scheme)
source_color                raw colour reported by the source (ÖO only)
running                     ``True``/``False`` when the source knows the state
unit_count                  number of involved units
units                       list of ``{name, code, started, ended}``
brigade / brigade_code      set on ``deployed_fire_brigade`` rows
==========================  ==================================================
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import datetime, timedelta, timezone, tzinfo
from html.parser import HTMLParser
from zoneinfo import ZoneInfo


def _vienna() -> tzinfo:
    """Europe/Vienna, with a fallback for systems without a tz database.

    Home Assistant always has one, but a plain Windows development box does
    not - there the local system timezone is the next best thing.
    """
    try:
        return ZoneInfo("Europe/Vienna")
    except Exception:  # noqa: BLE001 - ZoneInfoNotFoundError on Windows
        return datetime.now().astimezone().tzinfo or timezone.utc


TZ = _vienna()

# --------------------------------------------------------------------------- #
# categories / severity / colours
# --------------------------------------------------------------------------- #
CAT_FIRE = "fire"
CAT_TECHNICAL = "technical"
CAT_HAZARDOUS = "hazardous"
CAT_EXERCISE = "exercise"
CAT_SPECIAL = "special"
CAT_OTHER = "other"

CATEGORIES = (CAT_FIRE, CAT_TECHNICAL, CAT_HAZARDOUS, CAT_EXERCISE, CAT_SPECIAL, CAT_OTHER)

CATEGORY_LABELS = {
    CAT_FIRE: "Brand",
    CAT_TECHNICAL: "Technik",
    CAT_HAZARDOUS: "Gefahrgut",
    CAT_EXERCISE: "Übung",
    CAT_SPECIAL: "Sonder",
    CAT_OTHER: "Sonstiges",
}

_LETTER_CATEGORY = {
    "B": CAT_FIRE,
    "T": CAT_TECHNICAL,
    "S": CAT_HAZARDOUS,
    "G": CAT_HAZARDOUS,
    "U": CAT_EXERCISE,
}
_EXACT_CATEGORY = {
    "SOF": CAT_SPECIAL,
    "BA": CAT_SPECIAL,
    "BMA": CAT_FIRE,
}

SEVERITY_COLORS = {"high": "#dc2626", "medium": "#f59e0b", "low": "#2563eb", "info": "#6b7280"}
CATEGORY_COLORS = {
    CAT_FIRE: "#dc2626",
    CAT_TECHNICAL: "#2563eb",
    CAT_HAZARDOUS: "#16a34a",
    CAT_EXERCISE: "#6b7280",
    CAT_SPECIAL: "#7c3aed",
    CAT_OTHER: "#0891b2",
}
SOURCE_COLORS = {"noe": "#c1121f", "ooe": "#1d4ed8", "stmk": "#15803d", "custom": "#475569"}

#: colour scheme -> {lookup value: "#rrggbb"}
COLOR_SCHEMES: dict[str, dict[str, str]] = {
    "severity": SEVERITY_COLORS,
    "category": CATEGORY_COLORS,
    "source": SOURCE_COLORS,
}

#: ÖO. LFV uses a traffic light: red = fire, yellow = people in danger, blue = technical
SOURCE_COLOR_CATEGORY = {"red": CAT_FIRE, "yellow": CAT_TECHNICAL, "blue": CAT_TECHNICAL, "green": CAT_OTHER}
SOURCE_COLOR_SEVERITY = {"red": "high", "yellow": "medium", "blue": "low", "green": "low"}

_KEYWORD_RE = re.compile(r"^\s*([A-Za-z]{1,4})([0-9]{1,2})([A-Za-z]?)\b")
_WASTL_TS_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?")
_OOE_TS_RE = re.compile(r"(\d{2})\.(\d{2})\.(?:\s*(\d{1,2}):(\d{2}))?")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_DATE_DE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
_BRACKET_RE = re.compile(r"^\s*\([^)]*\)\s*:\s*")
_VOID_TAGS = {"br", "img", "hr", "meta", "link", "input", "source", "col", "wbr"}
_INLINE_TAGS = ("b", "strong", "a", "li", "title")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def clean_text(value: str | None) -> str:
    """Collapse whitespace and remove non breaking spaces."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ").replace("\u200b", "")).strip()


def decode_bytes(raw: bytes, charset_hint: str | None = None) -> str:
    """Decode a response body.

    Austrian fire brigade pages are a wild mix: the WASTL pages are
    ``windows-1252`` but do not announce a charset at all, ÖO is UTF-8 and the
    Styrian CSV is UTF-8 with a BOM.
    """
    hint = (charset_hint or "").strip().lower()
    if hint in ("utf-8", "utf8", "windows-1252", "cp1252", "iso-8859-15"):
        try:
            return _strip_bom(raw.decode(hint))
        except UnicodeDecodeError:
            pass
    try:
        return _strip_bom(raw.decode("utf-8"))
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _strip_bom(text: str) -> str:
    return text[1:] if text.startswith("\ufeff") else text


def split_keyword(text: str | None) -> tuple[str | None, str | None, int | None]:
    """Split an alert text into ``(letters, keyword, level)``.

    ``"B1 Gefahrenmeldeanlage - Brand"`` -> ``("B", "B1", 1)``
    ``"T03V-VU-mit-Verl"``               -> ``("T", "T03V", None)``
    ``"SOF1 Anforderung"``               -> ``("SOF", "SOF1", None)``
    ``"Brandverdacht"``                  -> ``(None, None, None)``

    Only single digit keywords are treated as a level, because Styrian
    keywords such as ``B06`` are type numbers and not severities.
    """
    if not text:
        return None, None, None
    match = _KEYWORD_RE.match(text)
    if not match:
        return None, None, None
    letters, digits, suffix = match.group(1).upper(), match.group(2), match.group(3).upper()
    level = int(digits) if len(digits) == 1 else None
    return letters, f"{letters}{digits}{suffix}", level


def category_for(letters: str | None, text: str | None = None) -> str:
    """Map an alert keyword (or a free text type) to a category."""
    if letters:
        if letters in _EXACT_CATEGORY:
            return _EXACT_CATEGORY[letters]
        if letters[0] in _LETTER_CATEGORY:
            return _LETTER_CATEGORY[letters[0]]
    lowered = (text or "").lower()
    if "übung" in lowered or "uebung" in lowered:
        return CAT_EXERCISE
    if "brand" in lowered:
        return CAT_FIRE
    if any(word in lowered for word in ("öl", "oel", "gefahrgut", "austritt")):
        return CAT_HAZARDOUS
    if "technisch" in lowered:
        return CAT_TECHNICAL
    return CAT_OTHER


def severity_for(category: str, level: int | None) -> str:
    """Derive a severity from the category and the numeric alarm level.

    This is a best effort mapping - ``keyword`` and ``level`` always carry the
    original values so automations can decide on their own.
    """
    if category == CAT_EXERCISE:
        return "info"
    if level is None:
        return "medium" if category == CAT_FIRE else "low"
    if level >= 2:
        return "high"
    if level == 1:
        return "medium"
    return "low"


def color_for(
    scheme: str,
    category: str,
    severity: str,
    source: str,
    source_color: str | None = None,
) -> str | None:
    """Return the colour of a row for the configured colour scheme."""
    if not scheme or scheme == "none":
        return None
    if scheme == "source_color":
        return SEVERITY_COLORS.get(severity) if not source_color else {
            "red": "#dc2626",
            "yellow": "#f59e0b",
            "blue": "#2563eb",
            "green": "#16a34a",
        }.get(source_color, SEVERITY_COLORS.get(severity))
    palette = COLOR_SCHEMES.get(scheme)
    if not palette:
        return None
    return palette.get(category if scheme == "category" else severity) or palette.get(source)


def color_legend(scheme: str) -> dict[str, str]:
    """Legend for a colour scheme, so dashboards can render a key."""
    if scheme == "severity":
        return dict(SEVERITY_COLORS)
    if scheme == "category":
        return {CATEGORY_LABELS.get(key, key): value for key, value in CATEGORY_COLORS.items()}
    if scheme == "source":
        return {key: value for key, value in SOURCE_COLORS.items() if key != "custom"}
    if scheme == "source_color":
        return {"rot": "#dc2626", "gelb": "#f59e0b", "blau": "#2563eb"}
    return {}


# --------------------------------------------------------------------------- #
# dates
# --------------------------------------------------------------------------- #
def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _resolve_year(day: int, month: int, now: datetime) -> int:
    """Guess the year for a ``DD.MM.`` timestamp.

    Sources that only print day and month (ÖO) would otherwise report January
    of the *next* year while looking at new year's eve data.
    """
    year = now.year
    if month - now.month > 6:
        year -= 1
    elif now.month - month > 6:
        year += 1
    return year


def _wastl_moment(raw: str) -> tuple[str | None, str | None]:
    """Return ``(started, age)`` for a WASTL date/time cell.

    The "aktuell" pages print ``19.09.2026 < 1 std.``, the history page prints
    ``19.09.2026 15:22:00``.
    """
    text = clean_text(raw)
    match = _WASTL_TS_RE.search(text)
    if not match:
        return None, None
    day, month, year = (int(match.group(index)) for index in (1, 2, 3))
    hour, minute, second = match.group(4), match.group(5), match.group(6)
    if hour and minute:
        started = datetime(year, month, day, int(hour), int(minute), int(second or 0), tzinfo=TZ)
        return _iso(started), None
    return None, clean_text(text[match.end() :]) or None


def _ooe_moment(text: str, now: datetime) -> str | None:
    """``"19.09. 15:12"`` -> ISO timestamp (the year is guessed)."""
    match = _OOE_TS_RE.search(clean_text(text))
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    hour, minute = match.group(3), match.group(4)
    moment = datetime(_resolve_year(day, month, now), month, day, tzinfo=TZ)
    if hour and minute:
        moment = moment.replace(hour=int(hour), minute=int(minute))
    return moment.isoformat()


def _ooe_end(text: str, started: str | None, now: datetime) -> str | None:
    """End time of an ÖO unit.

    ÖO prints the full stamp on the first timestamp but only ``HH:MM`` for the
    end of a mission (``19.09. 15:10 – 15:34``), so the day has to be taken
    over from the start.
    """
    text = clean_text(text)
    short = _TIME_RE.match(text)
    if short and started:
        start = datetime.fromisoformat(started)
        end = start.replace(hour=int(short.group(1)), minute=int(short.group(2)), second=0)
        if end < start:
            end += timedelta(days=1)
        return end.isoformat()
    return _ooe_moment(text, now)


# --------------------------------------------------------------------------- #
# forgiving HTML table parsing
# --------------------------------------------------------------------------- #
class _Cell:
    """A ``<td>`` with its text and the inline elements we care about."""

    __slots__ = ("text", "attrs", "elements")

    def __init__(self, attrs: dict[str, str] | None = None) -> None:
        self.text = ""
        self.attrs = attrs or {}
        self.elements: list[tuple[str, str, dict[str, str]]] = []

    def of(self, tag: str) -> list[tuple[str, dict[str, str]]]:
        return [(text, attrs) for name, text, attrs in self.elements if name == tag]

    def first(self, tag: str) -> tuple[str, dict[str, str]] | None:
        found = self.of(tag)
        return found[0] if found else None

    @property
    def plain(self) -> str:
        return clean_text(self.text)


class TableParser(HTMLParser):
    """Collect ``<tr>``/``<td>`` rows and keep ``<b>``, ``<a>`` and ``<li>``.

    The pages of all supported sources are hand written classic ASP/PHP tables:
    unclosed ``<li>`` tags, no ``<tbody>``, attributes without quotes.  A
    forgiving parser is therefore required.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_Cell]] = []
        self._row: list[_Cell] | None = None
        self._cell: _Cell | None = None
        self._stack: list[list] = []

    # -- helpers -------------------------------------------------------- #
    def _flush(self) -> None:
        if not self._stack:
            return
        tag, chunks, attrs = self._stack.pop()
        text = clean_text("".join(chunks))
        if tag in _INLINE_TAGS and self._cell is not None:
            self._cell.elements.append((tag, text, attrs))
        elif self._stack:
            self._stack[-1][1].append(text)

    # -- HTMLParser hooks ----------------------------------------------- #
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_dict = {key: (value or "") for key, value in attrs}
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = _Cell(attr_dict)
            if self._row is not None:
                self._row.append(self._cell)
        elif tag in _VOID_TAGS:
            return
        else:
            if tag == "li":
                self._flush()  # <li> is usually not closed on these pages
            self._stack.append([tag, [], attr_dict])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() not in _VOID_TAGS:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1][1].append(data)
        if self._cell is not None:
            self._cell.text += data

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "tr":
            if self._row:
                self.rows.append(self._row)
            self._row, self._cell, self._stack = None, None, []
            return
        if tag in ("td", "th"):
            self._cell = None
            return
        if tag in _VOID_TAGS:
            return
        if self._stack and self._stack[-1][0] == tag:
            self._flush()
            return
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                while len(self._stack) > index:
                    self._flush()
                return

    def close(self) -> None:  # noqa: D102 - inherited
        super().close()
        while self._stack:
            self._flush()
        if self._row:
            self.rows.append(self._row)
            self._row = None


def parse_html_rows(html: str) -> list[list[_Cell]]:
    """All ``<tr>`` rows of a document."""
    parser = TableParser()
    parser.feed(html)
    parser.close()
    return [row for row in parser.rows if len(row) > 1 or any(cell.plain for cell in row)]


def _is_header(row: list[_Cell]) -> bool:
    return any(cell.plain in ("Zeit", "Feuerwehr", "Einsatzart") for cell in row)


def make_id(*parts: object) -> str:
    """Stable short id built from the row contents."""
    raw = "|".join(str(part) for part in parts if part)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _cut_units(text: str, names: list[str]) -> str:
    """Remove every unit listing from an ÖO row text."""
    for name in names:
        if name and name in text:
            text = text.split(name, 1)[0]
    return text


# --------------------------------------------------------------------------- #
# source parsers
# --------------------------------------------------------------------------- #
def _finish(row: dict, source: dict, scheme: str, categories: list[str] | None) -> bool:
    """Fill derived fields, apply the category filter, return keep/drop."""
    category = row.get("category") or CAT_OTHER
    level = row.get("level")
    severity = row.get("severity") or severity_for(category, level)
    row["category"] = category
    row["severity"] = severity
    row["kind"] = source.get("kind")
    row["window"] = source.get("window", "custom")
    row["source"] = source.get("id")
    row["source_url"] = source.get("url")
    row["color"] = color_for(
        scheme, category, severity, source.get("id", "custom"), row.get("source_color")
    )
    started, ended = row.get("started"), row.get("ended")
    if started and ended:
        try:
            delta = datetime.fromisoformat(ended) - datetime.fromisoformat(started)
            row["duration_minutes"] = int(delta.total_seconds() // 60)
        except ValueError:
            row.pop("duration_minutes", None)
    if categories and category not in categories:
        return False
    return True


def parse_wastl_incidents(
    html: str, source: dict, now: datetime, scheme: str = "severity", categories: list[str] | None = None
) -> list[dict]:
    """Parse ``Land_EinsatzAktuell.asp`` and ``Land_EinsatzHistorie.asp``.

    Columns: ``[icon] | Leitstelle | Gemeinde | Einsatzart | DD.MM.YYYY [HH:MM]``.
    Column names follow the source: the second column is the alerting control
    centre (Alarmzentrale / BAZ Krems), not a district.
    """
    incidents: list[dict] = []
    for row in parse_html_rows(html):
        if len(row) < 4 or _is_header(row):
            continue
        cells = [cell.plain for cell in row]
        index = next((i for i, text in enumerate(cells) if i >= 3 and _WASTL_TS_RE.search(text)), None)
        if index is None:
            continue
        stamp = cells[index]
        started, age = _wastl_moment(stamp)
        alert_type = cells[index - 1] if index >= 1 else None
        letters, keyword, level = split_keyword(alert_type)
        date_match = _DATE_DE_RE.search(stamp)
        incident = {
            "id": make_id(source.get("id"), stamp, cells[index - 2] if index >= 2 else None, alert_type),
            "date": date_match.group(0) if date_match else None,
            "started": started,
            "age": age,
            "station": (cells[index - 3] if index >= 3 else None) or None,
            "municipality": (cells[index - 2] if index >= 2 else None) or None,
            "type": alert_type or None,
            "keyword": keyword,
            "level": level,
            "category": category_for(letters, alert_type),
        }
        if source.get("window") == "live":
            incident["running"] = True
        if _finish(incident, source, scheme, categories):
            incidents.append(incident)
    return incidents


def parse_wastl_units(
    html: str, source: dict, now: datetime, scheme: str = "severity", categories: list[str] | None = None
) -> list[dict]:
    """Parse ``Land_FFimEinsatz.asp`` - one row per deployed fire brigade.

    Columns: ``[icon] | 140302 Gemeinde | Einsatzart | DD.MM.YYYY < 1 std.``.
    The brigade number is kept - the old integration threw it away.
    """
    units: list[dict] = []
    for row in parse_html_rows(html):
        if len(row) < 3 or _is_header(row):
            continue
        cells = [cell.plain for cell in row]
        index = next((i for i, text in enumerate(cells) if i >= 2 and _WASTL_TS_RE.search(text)), None)
        if index is None:
            continue
        stamp = cells[index]
        started, age = _wastl_moment(stamp)
        alert_type = cells[index - 1]
        brigade_cell = cells[index - 2] if index >= 2 else ""
        brigade_match = re.match(r"^(\d+)\s+(.*)$", brigade_cell)
        if brigade_match:
            brigade_code, brigade = brigade_match.group(1), clean_text(brigade_match.group(2))
        else:
            brigade_code, brigade = None, brigade_cell
        letters, keyword, level = split_keyword(alert_type)
        date_match = _DATE_DE_RE.search(stamp)
        incident = {
            "id": make_id(source.get("id"), stamp, brigade_code or brigade, alert_type),
            "date": date_match.group(0) if date_match else None,
            "started": started,
            "age": age,
            "municipality": brigade,
            "brigade": brigade,
            "brigade_code": brigade_code,
            "type": alert_type,
            "keyword": keyword,
            "level": level,
            "category": category_for(letters, alert_type),
            "unit_count": 1,
            "running": True,
            "units": [{"name": brigade, "code": brigade_code, "started": started, "ended": None}],
        }
        if _finish(incident, source, scheme, categories):
            units.append(incident)
    return units


def parse_ooe(
    html: str, source: dict, now: datetime, scheme: str = "severity", categories: list[str] | None = None
) -> list[dict]:
    """Parse the ÖO. LFV list pages (``einsaetze.ooelfv.at``).

    Two columns per row: a colour chip and a cell packing everything else::

        <td style="background-color: red">&nbsp;</td>
        <td><b>Handenberg</b> (<a title="Braunau">BR</a>): Brandverdacht<br>
            <small><ul><li>Feuerwehr Handenberg: 19.09. 15:12 – 15:34</ul></small></td>

    ÖO prints the district abbreviation as link text and the full district name
    in the ``title`` attribute - both are kept.
    """
    incidents: list[dict] = []
    for row in parse_html_rows(html):
        if len(row) != 2:
            continue
        chip, body = row
        municipality_el = body.first("b")
        if not municipality_el:
            continue
        municipality = municipality_el[0]
        district_el = body.first("a")
        district_code = district_el[0] if district_el else None
        district = clean_text(district_el[1].get("title")) if district_el else None

        units: list[dict] = []
        for text, _attrs in body.of("li"):
            match = re.match(r"^(.*?):\s*(.*)$", text)
            name, times = (clean_text(match.group(1)), match.group(2)) if match else (text, "")
            parts = [clean_text(part) for part in re.split(r"\s+[–-]\s+", times) if clean_text(part)]
            started_unit = _ooe_moment(parts[0], now) if parts else None
            units.append(
                {
                    "name": name,
                    "code": None,
                    "started": started_unit,
                    "ended": _ooe_end(parts[1], started_unit, now) if len(parts) > 1 else None,
                }
            )

        alert_type = body.plain
        if alert_type.startswith(municipality):
            alert_type = alert_type[len(municipality) :]
        alert_type = clean_text(_BRACKET_RE.sub("", alert_type))
        alert_type = clean_text(_cut_units(alert_type, [unit["name"] for unit in units]))

        started = min((unit["started"] for unit in units if unit["started"]), default=None)
        ended = None
        if units and all(unit["ended"] for unit in units):
            ended = max(unit["ended"] for unit in units if unit["ended"])

        style = f"{chip.attrs.get('style', '')} {chip.attrs.get('class', '')}".lower()
        source_color = next(
            (colour for colour in ("red", "yellow", "blue", "green") if colour in style), None
        )
        letters, keyword, level = split_keyword(alert_type)
        category = category_for(letters, alert_type)
        if category == CAT_OTHER and source_color:
            category = SOURCE_COLOR_CATEGORY.get(source_color, CAT_OTHER)
        incident = {
            "id": make_id(source.get("id"), municipality, alert_type, started),
            "date": datetime.fromisoformat(started).strftime("%d.%m.%Y") if started else None,
            "started": started,
            "ended": ended,
            "time": started[11:16] if started else None,
            "municipality": municipality or None,
            "district": district or None,
            "district_code": district_code or None,
            "type": alert_type or None,
            "keyword": keyword,
            "level": level,
            "category": category,
            "severity": SOURCE_COLOR_SEVERITY.get(source_color or "", ""),
            "source_color": source_color,
            "running": ended is None,
            "unit_count": len(units),
            "units": units,
        }
        if _finish(incident, source, scheme, categories):
            incidents.append(incident)
    return incidents


def parse_stmk_csv(
    text: str, source: dict, now: datetime, scheme: str = "severity", categories: list[str] | None = None
) -> list[dict]:
    """Parse the Styrian ``Public.aspx`` CSV.

    ``date;assigned_units;tycod;s_name;esz;dgroup;sub_tycod`` - the list covers
    the last 24 hours and ``assigned_units > 0`` means the mission is running.
    This is the cleanest of all sources: delimiter separated, no HTML.
    """
    incidents: list[dict] = []
    for raw in csv.DictReader(io.StringIO(text), delimiter=";"):
        brigade = clean_text(raw.get("s_name"))
        if not brigade:
            continue
        alert_type = clean_text(raw.get("tycod"))
        sub = clean_text(raw.get("sub_tycod"))
        date_match = _DATE_DE_RE.search(clean_text(raw.get("date")))
        date_text = date_match.group(0) if date_match else None
        started = None
        if date_match:
            started = datetime(
                int(date_match.group(3)), int(date_match.group(2)), int(date_match.group(1)), tzinfo=TZ
            ).isoformat()
        letters, keyword, level = split_keyword(sub)
        try:
            unit_count = int(clean_text(raw.get("assigned_units")) or 0)
        except ValueError:
            unit_count = 0
        incident = {
            "id": make_id(source.get("id"), date_text, brigade, sub, raw.get("esz")),
            "date": date_text,
            "started": started,
            "municipality": brigade,
            "district_code": clean_text(raw.get("dgroup")) or None,
            "type": alert_type or sub or None,
            "keyword": keyword or (sub.split("-")[0] or None),
            "level": level,
            "category": category_for(letters, f"{alert_type} {sub}"),
            "unit_count": unit_count,
            "running": unit_count > 0,
            "date_only": True,
            "brigade": brigade,
            "brigade_code": clean_text(raw.get("esz")) or None,
        }
        if _finish(incident, source, scheme, categories):
            incidents.append(incident)
    return incidents


PARSERS = {
    "wastl_incidents": parse_wastl_incidents,
    "wastl_units": parse_wastl_units,
    "ooe": parse_ooe,
    "stmk_csv": parse_stmk_csv,
}


# --------------------------------------------------------------------------- #
# post processing
# --------------------------------------------------------------------------- #
def apply_row_filter(rows: list[dict], mode: str | None) -> list[dict]:
    """Keep only running (``ongoing``) or only finished (``closed``) rows."""
    if mode == "ongoing":
        return [row for row in rows if row.get("running") is True]
    if mode == "closed":
        return [row for row in rows if row.get("running") is False]
    return rows


def expand_units(rows: list[dict], source: dict, limit: int | None = None) -> list[dict]:
    """Turn incident rows into one row per involved unit.

    Used for sources that report the units per mission but have no dedicated
    "deployed brigades" page of their own.
    """
    units: list[dict] = []
    for row in rows:
        involved = list(row.get("units") or [])
        if not involved and row.get("brigade"):
            involved = [{"name": row["brigade"], "code": row.get("brigade_code")}]
        if not involved:
            involved = [{"name": row.get("municipality"), "code": None}]
        for index, unit in enumerate(involved):
            name = unit.get("name") or row.get("municipality")
            if not name:
                continue
            units.append(
                {
                    "id": make_id(source.get("id"), row.get("id"), name, index),
                    "source": row.get("source"),
                    "source_url": row.get("source_url"),
                    "kind": source.get("kind"),
                    "window": row.get("window"),
                    "date": row.get("date"),
                    "started": unit.get("started") or row.get("started"),
                    "ended": unit.get("ended") or row.get("ended"),
                    "time": row.get("time"),
                    "municipality": row.get("municipality"),
                    "district": row.get("district"),
                    "district_code": row.get("district_code"),
                    "type": row.get("type"),
                    "keyword": row.get("keyword"),
                    "level": row.get("level"),
                    "category": row.get("category"),
                    "severity": row.get("severity"),
                    "color": row.get("color"),
                    "source_color": row.get("source_color"),
                    "running": row.get("running"),
                    "unit_count": 1,
                    "brigade": name,
                    "brigade_code": unit.get("code"),
                }
            )
    return units[:limit] if limit else units


def summarize(rows: list[dict]) -> dict:
    """Aggregate a row list into counters the UI can use directly."""
    counters: dict[str, dict[str, int]] = {
        "by_category": {},
        "by_district": {},
        "by_keyword": {},
        "by_brigade": {},
    }
    for row in rows:
        for key, value in (
            ("by_category", row.get("category")),
            ("by_district", row.get("district") or row.get("district_code")),
            ("by_keyword", row.get("keyword")),
        ):
            if value:
                counters[key][value] = counters[key].get(value, 0) + 1
        involved = [unit.get("name") for unit in row.get("units") or []] or [row.get("brigade")]
        for name in involved:
            if name:
                counters["by_brigade"][name] = counters["by_brigade"].get(name, 0) + 1
    return {
        key: dict(sorted(value.items(), key=lambda item: (-item[1], item[0])))
        for key, value in counters.items()
    }


def parse_source(
    text: str,
    source: dict,
    now: datetime | None = None,
    scheme: str = "severity",
    categories: list[str] | None = None,
) -> list[dict]:
    """Parse one downloaded document into normalised rows."""
    parser = PARSERS.get(source.get("parser", ""))
    if parser is None:
        raise ValueError(f"unknown parser: {source.get('parser')!r}")
    rows = parser(text, source, now or datetime.now(TZ), scheme, categories)
    rows = apply_row_filter(rows, source.get("filter"))
    if source.get("expand") == "units":
        rows = expand_units(rows, source, source.get("limit"))
    return rows


def sort_rows(rows: list[dict], reverse: bool = True) -> list[dict]:
    """Newest first - sources are not consistently ordered."""
    return sorted(rows, key=lambda row: (row.get("started") or row.get("date") or ""), reverse=reverse)


def humanize_duration(minutes: int | None) -> str | None:
    """``95`` -> ``"1 h 35 min"``."""
    if minutes is None:
        return None
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h" if not rest else f"{hours} h {rest} min"
