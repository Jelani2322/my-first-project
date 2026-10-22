import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "config.example.json"
CONFIG = ROOT / "config.json"


def _merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path=None):
    """Defaults come from config.example.json; config.json (if present) overrides them."""
    cfg = json.loads(EXAMPLE.read_text())
    path = Path(path) if path else CONFIG
    if path.exists():
        cfg = _merge(cfg, json.loads(path.read_text()))
    return cfg
