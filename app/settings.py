"""일반 설정(비밀 아님). 버전이 바뀌어 형식이 달라지면 MIGRATIONS로 자동 변환한다."""
import copy
import json
import threading

from . import paths

SCHEMA = 1

DEFAULTS = {
    "schema": SCHEMA,
    "claude_model": "claude-opus-5-5",
    "whisper_model": "auto",  # auto | large-v3-turbo | medium | small
    "defaults": {"made_for_kids": False, "synthetic": False, "paid": False},
}

# 예: MIGRATIONS[1] = lambda cfg: {...}  # schema 1 -> 2
MIGRATIONS: dict = {}

_lock = threading.Lock()


def _merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    with _lock:
        cfg = {}
        if paths.SETTINGS_FILE.exists():
            try:
                cfg = json.loads(paths.SETTINGS_FILE.read_text("utf-8"))
            except Exception:
                cfg = {}
        ver = cfg.get("schema", SCHEMA)
        while ver < SCHEMA and ver in MIGRATIONS:
            cfg = MIGRATIONS[ver](cfg)
            ver += 1
            cfg["schema"] = ver
        return _merge(DEFAULTS, cfg)


def update(patch: dict) -> dict:
    cfg = _merge(load(), patch)
    with _lock:
        paths.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = paths.SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(paths.SETTINGS_FILE)
    return cfg
