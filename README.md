# lecture5-frameworks
Follow along with the code for lecture 5.

## Follow along in lecture (do this before class)

```bash
git clone https://github.com/cs329z/lecture5-frameworks.git
cd lecture5-frameworks
./setup.sh
```

`setup.sh` installs `uv` if you don't have it, installs Python 3.12 and every dependency, asks for your
OpenRouter API key once (saved to the gitignored `.env`), and opens `lecture5.ipynb` in VS Code if it's
installed. In VS Code pick the `.venv` (Python 3.12) kernel. On Windows, run it from Git Bash.

Running the whole notebook once costs about one cent of OpenRouter credit.

Things to know while following along:
- Cells run top to bottom. Parts 2 and 3 reuse objects from Part 1.
- The tinycal calendar opens in a browser tab when the setup cell runs; keep it next to the notebook.
  (Or run `uv run python -m tinycal` in a separate terminal so it survives kernel restarts.)
- The GEPA optimization cell takes about 3 minutes. Start it and keep listening.
- Model outputs vary a little between runs (tool order, wording). That's expected.
- If the Temporal cell says the dev server "did not start", an old kernel is holding port 8233: restart the kernel.
- Re-running cells is cheap: LLM calls are cached on disk (see below).

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it, then run:

```bash
uv sync
```

That installs Python 3.12 (if needed), creates a `.venv`, and installs DSPy, LangGraph, and Temporal
plus Jupyter. Run anything with `uv run`, e.g.:

```bash
uv run python script.py
uv run jupyter lab
```

The notebook starts a local Temporal dev server itself (the SDK downloads the binary on first run),
so no separate install is needed on macOS, Linux, or Windows. If you'd rather run it standalone,
install the [Temporal CLI](https://docs.temporal.io/cli#install) and run `temporal server start-dev`.

Copy `.env.example` to `.env` and fill in your `OPENROUTER_API_KEY`. `.env` is gitignored.

LLM calls are cached on disk so re-running cells is free and deterministic: DSPy does this by default
(`~/.dspy_cache`); for LangGraph the setup cell installs `llm_cache.SQLiteLLMCache` (a 30-line helper in this
repo) into LangChain's global cache, stored in the gitignored `.langchain_cache.db`.

## tinycal: the calendar app the agents control

`tinycal/` is a dependency-free calendar (stdlib only) with a live web UI and a Python SDK
whose functions double as agent tools. Run it standalone:

```bash
uv run python -m tinycal        # opens http://localhost:8765 in your browser
```

Or start it from inside a notebook and use the SDK directly:

```python
import tinycal
tinycal.ensure_server()              # starts the server in a background thread if needed
print(tinycal.api())                 # condensed listing of every function below
tinycal.today()                      # "2026-10-03 (Saturday)"
tinycal.add_event("Dentist", "2026-10-07", "09:00", notes="bring insurance card")  # 1 hour by default
tinycal.add_event("Standup", "2026-10-07", "14:00", duration_minutes=15, emoji="🧍")
tinycal.list_events("2026-10-07")    # events on one day; or (start_date, end_date) for a range
tinycal.find_free_slots("2026-10-07", duration_minutes=60)
tinycal.update_event(event_id, end="10:30")
tinycal.delete_event(event_id)
tinycal.clear_calendar()             # remove everything
```

The UI polls every second, so tool calls made by an agent show up immediately. Events live in
`tinycal/events.json` (gitignored). Bad inputs raise `tinycal.CalendarError` with a message the
agent can read and recover from.

## Data

`data/emails.json` holds 50 synthetic but realistic emails, each labeled with the event's name,
date, start time, and duration. The notebook uses it to measure a small model before and after
GEPA optimization. Regenerate it (deterministic) with:

```bash
uv run python data/make_emails.py
```
