"""깃허브 Releases에서 새 버전을 확인하고, 설치본이면 내려받아 덮어쓰기 설치한다.

설치 파일은 사용자 데이터 폴더(%APPDATA%\\G-UPLOADER)를 건드리지 않으므로 설정은 유지된다.
"""
import hashlib
import os
import subprocess
import sys
import threading

import httpx

from . import UPDATE_REPO, __version__, paths

_cache = None


class UpdateError(RuntimeError):
    pass


def _ver(s: str) -> tuple:
    nums = []
    for p in s.lstrip("vV").split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        nums.append(int(digits or 0))
    return tuple(nums + [0] * (3 - len(nums)))


def installed() -> bool:
    return bool(getattr(sys, "frozen", False))


def check() -> dict:
    global _cache
    if not UPDATE_REPO:
        _cache = {"enabled": False, "current": __version__}
        return _cache
    try:
        r = httpx.get(f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest",
                      headers={"Accept": "application/vnd.github+json"}, timeout=10,
                      follow_redirects=True)
        r.raise_for_status()
        rel = r.json()
    except Exception:
        raise UpdateError("업데이트 정보를 가져오지 못했습니다. 인터넷 연결을 확인해 주세요.")
    latest = rel.get("tag_name", "").lstrip("vV")
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    setup = next((n for n in assets if n.lower().endswith(".exe") and "setup" in n.lower()), None)
    _cache = {
        "enabled": True,
        "current": __version__,
        "latest": latest,
        "newer": bool(latest) and _ver(latest) > _ver(__version__),
        "notes": (rel.get("body") or "")[:3000],
        "page": rel.get("html_url", ""),
        "setup_url": assets.get(setup) if setup else None,
        "setup_name": setup,
        "sums_url": assets.get("SHA256SUMS.txt"),
        "installed": installed(),
    }
    return _cache


def cached():
    return _cache


def install() -> None:
    info = _cache or check()
    if not info.get("newer"):
        raise UpdateError("이미 최신 버전입니다.")
    if not installed():
        raise UpdateError("소스 코드로 실행 중입니다. 프로그램 폴더에서 'git pull'로 업데이트해 주세요.")
    if not info.get("setup_url") or not info.get("sums_url"):
        raise UpdateError("이 릴리스에 설치 파일이 없습니다.")

    paths.UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    dst = paths.UPDATES_DIR / info["setup_name"]
    try:
        sums = httpx.get(info["sums_url"], timeout=30, follow_redirects=True).text
        h = hashlib.sha256()
        with httpx.stream("GET", info["setup_url"], timeout=120, follow_redirects=True) as r:
            r.raise_for_status()
            with open(dst, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    h.update(chunk)
    except Exception:
        raise UpdateError("설치 파일을 내려받지 못했습니다.")

    expected = None
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == info["setup_name"]:
            expected = parts[0].lower()
    if expected != h.hexdigest():
        dst.unlink(missing_ok=True)
        raise UpdateError("설치 파일 검사에 실패했습니다(파일 손상). 다시 시도해 주세요.")

    # 설치 프로그램이 이 앱을 닫고 덮어쓴 뒤 다시 실행한다.
    subprocess.Popen([str(dst), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                     close_fds=True, creationflags=0x00000008 if os.name == "nt" else 0)
    threading.Timer(1.5, lambda: os._exit(0)).start()
