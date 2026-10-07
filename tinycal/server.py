"""A tiny calendar HTTP server using only the Python standard library.

Events are stored in a JSON file next to this module and shown in a live web UI.

API (all JSON):
    GET    /api/today                      -> {"date": "YYYY-MM-DD", "weekday": "Monday"}
    GET    /api/events[?start=&end=]       -> [event, ...]   (inclusive date range; omit for all)
    POST   /api/events                     -> event          body: {title, date, start, end?, duration_minutes?, notes?, emoji?}
                                                             (no end: start + duration_minutes, default 60)
    PATCH  /api/events/<id>                -> event          body: any subset of the fields above
    DELETE /api/events/<id>                -> {"deleted": id}
    POST   /api/clear                      -> {"ok": true}   remove every event
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DATA_FILE = Path(__file__).with_name("events.json")
_LOCK = threading.Lock()
_EVENTS: dict[str, dict] = {}

FIELDS = ("title", "date", "start", "end", "notes", "emoji")


# --------------------------------------------------------------------------- storage


def _load() -> None:
    global _EVENTS
    if DATA_FILE.exists():
        try:
            _EVENTS = {e["id"]: e for e in json.loads(DATA_FILE.read_text("utf-8"))}
            return
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    _EVENTS = {}


def _save() -> None:
    DATA_FILE.write_text(json.dumps(_sorted_events(), indent=2), "utf-8")


def _sorted_events(start: str | None = None, end: str | None = None) -> list[dict]:
    evs = _EVENTS.values()
    if start:
        evs = (e for e in evs if e["date"] >= start)
    if end:
        evs = (e for e in evs if e["date"] <= end)
    return sorted(evs, key=lambda e: (e["date"], e["start"], e["title"]))



# --------------------------------------------------------------------------- validation


class BadRequest(Exception):
    pass


def _validate(fields: dict, *, partial: bool) -> dict:
    clean = {}
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise BadRequest(f"unknown field(s): {', '.join(sorted(unknown))}")
    if not partial:
        missing = [f for f in ("title", "date", "start") if f not in fields]
        if missing:
            raise BadRequest(f"missing required field(s): {', '.join(missing)}")
    for key, val in fields.items():
        if not isinstance(val, str):
            raise BadRequest(f"{key} must be a string")
        val = val.strip()
        if key == "title" and not val:
            raise BadRequest("title must not be empty")
        if key == "date":
            try:
                val = date.fromisoformat(val).isoformat()
            except ValueError:
                raise BadRequest(f"date must be YYYY-MM-DD, got {val!r}")
        if key in ("start", "end"):
            try:
                val = datetime.strptime(val[:5], "%H:%M").strftime("%H:%M")  # accepts HH:MM or HH:MM:SS
            except ValueError:
                raise BadRequest(f"{key} must be HH:MM (24-hour), got {val!r}")
        if key == "emoji" and len(val) > 8:
            raise BadRequest(f"emoji must be a single emoji, got {val!r}")
        clean[key] = val
    return clean


def _check_order(ev: dict) -> None:
    if ev["end"] < ev["start"]:
        raise BadRequest(f"end {ev['end']} is before start {ev['start']}")


def _insert(fields: dict) -> dict:
    fields = dict(fields)
    duration = fields.pop("duration_minutes", None)
    ev = {"id": uuid.uuid4().hex[:8], "notes": "", "emoji": ""}
    ev.update(_validate(fields, partial=False))
    if "end" not in ev:  # default: one hour after start, or the given duration, capped at end of day
        if duration is not None and (not isinstance(duration, int) or duration < 0):
            raise BadRequest(f"duration_minutes must be a non-negative integer, got {duration!r}")
        start = datetime.strptime(ev["start"], "%H:%M")
        end = min(start + timedelta(minutes=60 if duration is None else duration), start.replace(hour=23, minute=59))
        ev["end"] = end.strftime("%H:%M")
    _check_order(ev)
    _EVENTS[ev["id"]] = ev
    return ev


# --------------------------------------------------------------------------- HTTP


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):  # keep the console quiet
        pass

    # helpers
    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n == 0:
            return {}
        try:
            data = json.loads(self.rfile.read(n))
        except json.JSONDecodeError:
            raise BadRequest("body must be valid JSON")
        if not isinstance(data, dict):
            raise BadRequest("body must be a JSON object")
        return data

    def _route(self, method: str) -> None:
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if method == "GET" and parts == []:
                return self._html()
            if parts[:1] != ["api"]:
                return self._json(404, {"error": "not found"})
            with _LOCK:
                return self._api(method, parts[1:], q)
        except BadRequest as e:
            self._json(400, {"error": str(e)})
        except Exception as e:  # pragma: no cover
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def _api(self, method: str, parts: list[str], q: dict) -> None:
        if parts == ["today"] and method == "GET":
            t = date.today()
            return self._json(200, {"date": t.isoformat(), "weekday": t.strftime("%A")})

        if parts == ["events"]:
            if method == "GET":
                return self._json(200, _sorted_events(q.get("start"), q.get("end")))
            if method == "POST":
                ev = _insert(self._body())
                _save()
                return self._json(201, ev)

        if len(parts) == 2 and parts[0] == "events":
            ev = _EVENTS.get(parts[1])
            if ev is None:
                return self._json(404, {"error": f"no event with id {parts[1]!r}"})
            if method == "DELETE":
                del _EVENTS[ev["id"]]
                _save()
                return self._json(200, {"deleted": ev["id"]})
            if method == "PATCH":
                updated = {**ev, **_validate(self._body(), partial=True)}
                _check_order(updated)
                _EVENTS[ev["id"]] = updated
                _save()
                return self._json(200, updated)

        if parts == ["clear"] and method == "POST":
            _EVENTS.clear()
            _save()
            return self._json(200, {"ok": True})

        return self._json(404, {"error": "not found"})

    def _html(self) -> None:
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PATCH(self):
        self._route("PATCH")

    def do_DELETE(self):
        self._route("DELETE")


def make_server(port: int = 8765) -> ThreadingHTTPServer:
    with _LOCK:
        _load()
        _save()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    return srv


def serve(port: int = 8765) -> None:
    make_server(port).serve_forever()


# --------------------------------------------------------------------------- UI

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>tinycal</title>
<style>
  :root { --bg:#f6f7f9; --card:#fff; --line:#e3e6ea; --text:#1f2328; --muted:#6b7280;
          --accent:#2563eb; --today:#eef4ff; --danger:#b91c1c; }
  * { box-sizing: border-box; }
  body { margin:0; font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         background:var(--bg); color:var(--text); }
  header { display:flex; align-items:center; gap:12px; padding:12px 16px; background:var(--card);
           border-bottom:1px solid var(--line); flex-wrap:wrap; }
  header h1 { font-size:18px; margin:0 8px 0 0; }
  header .range { font-weight:600; min-width:220px; }
  header .spacer { flex:1; }
  button { font:inherit; padding:6px 12px; border:1px solid var(--line); background:var(--card);
           border-radius:6px; cursor:pointer; }
  button:hover { background:#f0f2f5; }
  button.danger { color:var(--danger); }
  main { padding:16px; }
  .week { display:grid; grid-template-columns: repeat(7, minmax(0,1fr)); gap:8px; }
  .day { background:var(--card); border:1px solid var(--line); border-radius:8px; min-height:60vh;
         display:flex; flex-direction:column; }
  .day.today { background:var(--today); border-color:var(--accent); }
  .day h2 { font-size:13px; margin:0; padding:8px 10px; border-bottom:1px solid var(--line); color:var(--muted); }
  .day.today h2 { color:var(--accent); }
  .day h2 b { display:block; font-size:18px; color:var(--text); }
  .events { padding:8px; display:flex; flex-direction:column; gap:6px; }
  .ev { border-left:3px solid var(--accent); background:#fff; border-radius:4px; padding:6px 8px;
        box-shadow:0 1px 2px rgba(0,0,0,.06); }
  .ev .time { font-size:12px; color:var(--muted); }
  .ev .title { font-weight:600; }
  .ev .notes { font-size:12px; color:var(--muted); white-space:pre-wrap; }
  .ev .del { float:right; border:none; background:none; color:var(--muted); padding:0 2px; font-size:14px; }
  .ev .del:hover { color:var(--danger); }
  .empty { color:var(--muted); font-size:12px; padding:8px; }
  .status { font-size:12px; color:var(--muted); }
  @media (max-width: 900px) { .week { grid-template-columns: 1fr; } .day { min-height:auto; } }
</style>
</head>
<body>
<header>
  <h1>tinycal</h1>
  <button id="prev">&lsaquo;</button>
  <button id="todayBtn">Today</button>
  <button id="next">&rsaquo;</button>
  <span class="range" id="range"></span>
  <span class="spacer"></span>
  <span class="status" id="status"></span>
  <button class="danger" id="clear">Clear</button>
</header>
<main><div class="week" id="week"></div></main>
<script>
const DAY = 86400000;
const pad = n => String(n).padStart(2, "0");
const iso = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
const parse = s => { const [y,m,d] = s.split("-").map(Number); return new Date(y, m-1, d); };
const fmt12 = t => { let [h,m] = t.split(":").map(Number); const ap = h >= 12 ? "pm" : "am"; h = h % 12 || 12; return `${h}:${pad(m)}${ap}`; };
const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

let weekStart = startOfWeek(new Date());
function startOfWeek(d) { d = new Date(d.getFullYear(), d.getMonth(), d.getDate()); d.setDate(d.getDate() - d.getDay()); return d; }

async function api(method, path, body) {
  const r = await fetch(path, { method, headers: body ? {"Content-Type": "application/json"} : {}, body: body ? JSON.stringify(body) : undefined });
  return r.json();
}

let lastJson = "";
async function refresh(force) {
  const end = new Date(weekStart.getTime() + 6*DAY);
  let events;
  try {
    events = await api("GET", `/api/events?start=${iso(weekStart)}&end=${iso(end)}`);
    document.getElementById("status").textContent = "live";
  } catch (e) {
    document.getElementById("status").textContent = "server unreachable";
    return;
  }
  const key = iso(weekStart) + JSON.stringify(events);
  if (!force && key === lastJson) return;
  lastJson = key;

  const opts = { month: "short", day: "numeric" };
  document.getElementById("range").textContent =
    `${weekStart.toLocaleDateString(undefined, opts)} – ${end.toLocaleDateString(undefined, {...opts, year: "numeric"})}`;

  const todayIso = iso(new Date());
  const week = document.getElementById("week");
  week.innerHTML = "";
  for (let i = 0; i < 7; i++) {
    const d = new Date(weekStart.getTime() + i*DAY);
    const dIso = iso(d);
    const col = document.createElement("div");
    col.className = "day" + (dIso === todayIso ? " today" : "");
    const evs = events.filter(e => e.date === dIso);
    col.innerHTML = `<h2>${d.toLocaleDateString(undefined, {weekday: "short"})}<b>${d.getDate()}</b></h2>
      <div class="events">${evs.length ? evs.map(e => `
        <div class="ev" data-id="${e.id}">
          <button class="del" title="delete">&times;</button>
          <div class="time">${fmt12(e.start)}${e.end !== e.start ? " – " + fmt12(e.end) : ""}</div>
          <div class="title">${e.emoji ? esc(e.emoji) + " " : ""}${esc(e.title)}</div>
          ${e.notes ? `<div class="notes">${esc(e.notes)}</div>` : ""}
        </div>`).join("") : `<div class="empty">no events</div>`}</div>`;
    week.appendChild(col);
  }
}

document.getElementById("week").addEventListener("click", async e => {
  if (!e.target.classList.contains("del")) return;
  await api("DELETE", `/api/events/${e.target.closest(".ev").dataset.id}`);
  refresh(true);
});
document.getElementById("prev").onclick = () => { weekStart = new Date(weekStart.getTime() - 7*DAY); refresh(true); };
document.getElementById("next").onclick = () => { weekStart = new Date(weekStart.getTime() + 7*DAY); refresh(true); };
document.getElementById("todayBtn").onclick = () => { weekStart = startOfWeek(new Date()); refresh(true); };
document.getElementById("clear").onclick = async () => { await api("POST", "/api/clear"); refresh(true); };

refresh(true);
setInterval(() => refresh(false), 1000);
</script>
</body>
</html>
"""
