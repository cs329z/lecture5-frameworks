"""A persistent prompt -> response cache for LangChain chat models, like DSPy's disk cache.

Usage (once, at setup):
    from langchain_core.globals import set_llm_cache
    from llm_cache import SQLiteLLMCache
    set_llm_cache(SQLiteLLMCache(".langchain_cache.db"))

Identical model calls (same messages, same model settings) are then replayed from disk instead of
being sent to the provider, so re-running a cell is free and deterministic.
"""

import pickle
import sqlite3
import threading

from langchain_core.caches import BaseCache


class SQLiteLLMCache(BaseCache):
    def __init__(self, path: str = ".langchain_cache.db"):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS cache (prompt TEXT, llm TEXT, value BLOB, PRIMARY KEY (prompt, llm))")
        self._lock = threading.Lock()

    def lookup(self, prompt: str, llm_string: str):
        with self._lock:
            row = self._db.execute("SELECT value FROM cache WHERE prompt = ? AND llm = ?", (prompt, llm_string)).fetchone()
        return pickle.loads(row[0]) if row else None

    def update(self, prompt: str, llm_string: str, return_val) -> None:
        value = pickle.dumps(list(return_val))
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (prompt, llm_string, value))
            self._db.commit()

    def clear(self, **kwargs) -> None:
        with self._lock:
            self._db.execute("DELETE FROM cache")
            self._db.commit()
