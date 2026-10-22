"""Small JSON file that remembers today's goal, alerts and your open/closed trades."""
import json
from datetime import date
from pathlib import Path

from .config import ROOT


class Store:
    def __init__(self, demo=False):
        self.path = ROOT / ("state.demo.json" if demo else "state.json")

    def load(self):
        st = json.loads(self.path.read_text()) if self.path.exists() else {}
        st.setdefault("alerts", [])
        st.setdefault("positions", [])
        st.setdefault("closed", [])
        st.setdefault("validations", {})
        st.setdefault("next_id", 1)
        return st

    def save(self, st):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=2, default=str))
        tmp.replace(self.path)

    @staticmethod
    def new_id(st):
        i = st["next_id"]
        st["next_id"] += 1
        return i

    @staticmethod
    def realized_today(st, today=None):
        today = (today or date.today()).isoformat()
        return sum(c["pnl"] for c in st["closed"] if c["closed_at"][:10] == today)
