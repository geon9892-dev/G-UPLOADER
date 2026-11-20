"""프로그램 파일과 사용자 데이터 위치.

사용자 데이터(설정, 키, 정체성 파일, 기록, Whisper 모델)는 프로그램 폴더와 분리해
업데이트로 프로그램을 덮어써도 지워지지 않게 한다.
"""
import os
import sys
from pathlib import Path

APP_NAME = "G-UPLOADER"


def _data_dir() -> Path:
    env = os.environ.get("GUP_DATA_DIR")
    if env:
        return Path(env)
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def app_root() -> Path:
    """소스 실행이면 저장소 루트, 설치본(PyInstaller)이면 번들 폴더."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return app_root()


DATA_DIR = _data_dir()
MODELS_DIR = DATA_DIR / "models"
IDENTITY_DIR = DATA_DIR / "identity"
HISTORY_DIR = DATA_DIR / "history"
WORK_DIR = DATA_DIR / "work"
UPDATES_DIR = DATA_DIR / "updates"
SETTINGS_FILE = DATA_DIR / "settings.json"
SECRETS_FILE = DATA_DIR / "secrets.bin"

STATIC_DIR = app_root() / "app" / "static"
TEMPLATES_DIR = app_root() / "templates"


def ensure_dirs() -> None:
    for d in (DATA_DIR, MODELS_DIR, IDENTITY_DIR, HISTORY_DIR, WORK_DIR, UPDATES_DIR):
        d.mkdir(parents=True, exist_ok=True)
