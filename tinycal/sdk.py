"""Python SDK for tinycal. Every public function is a plain, typed function with a
docstring, so it can be handed directly to DSPy (`dspy.ReAct(..., tools=[...])`) or
LangChain (`@tool` / `create_agent(tools=[...])`) as a tool.

Dates are "YYYY-MM-DD" strings and times are 24-hour "HH:MM" strings
(datetime.date / datetime.time objects are accepted too).
Errors are raised as CalendarError with a human-readable message, which is what
an agent should see when it calls a tool incorrectly.
"""

from __future__ import annotations

import http.client
import inspect
import json
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timedelta

BASE_URL = "http://127.0.0.1:8765"


class CalendarError(Exception):
    """Raised when the calendar rejects a request (bad input, missing event, server down)."""


# --------------------------------------------------------------------------- transport


def _request(method: str, path: str, body: dict | None = None, timeout: float = 5):
    data = json.dumps(body, default=str).encode("utf-8") if body is not None else None  # date/time -> str
    req = urllib.request.Request(BASE_URL + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", e.reason)
        except Exception:
            msg = e.reason
        raise CalendarError(msg) from None
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError):
        # connection refused, timeout, or something on the port that isn't tinycal
        raise CalendarError(
            f"calendar server not reachable at {BASE_URL}; run `python -m tinycal` "
            "or call tinycal.ensure_server()"
        ) from None


def is_running() -> bool:
    """Return True if the calendar server is reachable."""
    try:
        _request("GET", "/api/today", timeout=1)
        return True
    except CalendarError:
        return False


def ensure_server(open_browser: bool = True) -> str:
    """Start the calendar server in a background thread if it isn't already running.

    Safe to call repeatedly (e.g. at the top of a notebook). Returns the UI URL.

    Note: a server started this way lives only as long as the calling process
    (e.g. the notebook kernel). For a long session, run `python -m tinycal` in a
    separate terminal instead; this function then just detects it.
    """
    if not is_running():
        from .server import make_server

        port = int(BASE_URL.rsplit(":", 1)[1])
        try:
            srv = make_server(port)
        except OSError as e:
            raise CalendarError(f"port {port} is in use but not answering as tinycal: {e}") from None
        threading.Thread(target=srv.serve_forever, daemon=True, name="tinycal").start()
        for _ in range(50):  # wait until the server answers before handing out the URL
            if is_running():
                break
            time.sleep(0.1)
        else:
            raise CalendarError("tinycal server thread started but is not answering")
        if open_browser:
            webbrowser.open(BASE_URL)
    return BASE_URL


# --------------------------------------------------------------------------- tools


def today() -> str:
    """Get today's date and weekday, e.g. "2026-10-03 (Saturday)"."""
    t = _request("GET", "/api/today")
    return f"{t['date']} ({t['weekday']})"


def list_events(start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """List calendar events, sorted by date and start time.

    Args:
        start_date: first date to include, "YYYY-MM-DD". Omit for no lower bound.
        end_date: last date to include, "YYYY-MM-DD". Omit to use start_date
            (a single day), or no upper bound if start_date is also omitted.

    Returns a list of events, each a dict with keys id, title, date, start, end, notes, emoji.
    """
    if start_date and not end_date:
        end_date = start_date
    q = []
    if start_date:
        q.append(f"start={start_date}")
    if end_date:
        q.append(f"end={end_date}")
    return _request("GET", "/api/events" + ("?" + "&".join(q) if q else ""))


def add_event(
    title: str,
    date: str,
    start: str,
    end: str | None = None,
    duration_minutes: int | None = None,
    notes: str = "",
    emoji: str = "",
) -> dict:
    """Add an event to the calendar.

    Args:
        title: short name of the event, e.g. "Dentist".
        date: "YYYY-MM-DD".
        start: start time, 24-hour "HH:MM", e.g. "14:30".
        end: end time, 24-hour "HH:MM". Optional.
        duration_minutes: alternative to end. If neither is given the event lasts one hour.
        notes: optional free-text details such as a location.
        emoji: optional single emoji shown next to the title, e.g. "🦷".

    Returns the created event including its generated id.
    """
    body = {"title": title, "date": date, "start": start, "notes": notes, "emoji": emoji}
    if end is not None:
        body["end"] = end
    elif duration_minutes is not None:
        body["duration_minutes"] = duration_minutes
    return _request("POST", "/api/events", body)


def update_event(
    event_id: str,
    title: str | None = None,
    date: str | None = None,
    start: str | None = None,
    end: str | None = None,
    notes: str | None = None,
    emoji: str | None = None,
) -> dict:
    """Change one or more fields of an existing event. Only the given fields are changed.

    Args:
        event_id: id of the event (from list_events or add_event).
        title: new title.
        date: new date, "YYYY-MM-DD".
        start: new start time, "HH:MM".
        end: new end time, "HH:MM".
        notes: new notes text.
        emoji: new emoji.

    Returns the updated event.
    """
    fields = {k: v for k, v in dict(title=title, date=date, start=start, end=end, notes=notes, emoji=emoji).items() if v is not None}
    if not fields:
        raise CalendarError("update_event: give at least one field to change")
    return _request("PATCH", f"/api/events/{event_id}", fields)


def delete_event(event_id: str) -> str:
    """Delete an event by id. Returns a confirmation message."""
    r = _request("DELETE", f"/api/events/{event_id}")
    return f"deleted event {r['deleted']}"


def find_free_slots(date: str, duration_minutes: int = 60, day_start: str = "09:00", day_end: str = "18:00") -> list[str]:
    """Find open time windows on a date that can fit an event of the given length.

    Args:
        date: "YYYY-MM-DD".
        duration_minutes: minimum length of a free window.
        day_start: earliest time to consider, "HH:MM" (default 09:00).
        day_end: latest time to consider, "HH:MM" (default 18:00).

    Returns a list of free windows like ["09:00-10:30", "13:00-18:00"].
    """
    fmt = "%H:%M"
    cur = datetime.strptime(day_start, fmt)
    stop = datetime.strptime(day_end, fmt)
    need = timedelta(minutes=duration_minutes)
    free = []
    for ev in list_events(date):
        s, e = datetime.strptime(ev["start"], fmt), datetime.strptime(ev["end"], fmt)
        if s - cur >= need:
            free.append(f"{cur.strftime(fmt)}-{s.strftime(fmt)}")
        cur = max(cur, e)
    if stop - cur >= need:
        free.append(f"{cur.strftime(fmt)}-{stop.strftime(fmt)}")
    return free


def clear_calendar() -> str:
    """Delete every event in the calendar. Returns a confirmation message."""
    _request("POST", "/api/clear")
    return "calendar cleared"



# --------------------------------------------------------------------------- introspection

TOOLS = [today, list_events, add_event, update_event, delete_event, find_free_slots, clear_calendar]


class _Text(str):
    """A str that displays without quotes/escapes when it is the last expression in a notebook cell."""

    def __repr__(self) -> str:
        return str(self)


def api(full: bool = False) -> str:
    """Return a condensed listing of the SDK's tool functions.

    Args:
        full: include each function's complete docstring instead of just its first line.
    """
    rows = []
    for fn in TOOLS:
        sig = inspect.signature(fn)
        params = ", ".join(
            name if p.default is p.empty else f"{name}={p.default!r}" for name, p in sig.parameters.items()
        )
        ret = sig.return_annotation if isinstance(sig.return_annotation, str) else getattr(sig.return_annotation, "__name__", "")
        doc = inspect.getdoc(fn) or ""
        rows.append((f"{fn.__name__}({params})", f"-> {ret}", doc))

    width = max(len(call) for call, _, _ in rows)
    lines = [f"tinycal SDK  ({BASE_URL})", ""]
    for call, ret, doc in rows:
        summary = doc.splitlines()[0] if doc else ""
        lines.append(f"  {call:<{width}}  {ret:<12} {summary}")
        rest = [l for l in doc.splitlines()[1:] if l.strip()] if full else []
        if rest:
            lines.extend("      " + l for l in rest)
            lines.append("")
    lines += ["", "  Dates are 'YYYY-MM-DD', times are 24-hour 'HH:MM'. Errors raise CalendarError."]
    return _Text("\n".join(lines))
