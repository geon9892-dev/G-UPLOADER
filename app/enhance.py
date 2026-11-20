"""썸네일용 고화질: 원본에서 가장 선명한 프레임 고르기, AI 업스케일(Real-ESRGAN)."""
import os
import shutil
import subprocess
import threading
import uuid
import zipfile
from pathlib import Path

import httpx

from . import media, paths

HQ_DIR = paths.WORK_DIR / "hq"
TOOL_DIR = paths.DATA_DIR / "tools" / "realesrgan"
# xinntao/Real-ESRGAN 공식 릴리스 (BSD-3-Clause). 처음 쓸 때 한 번만 내려받는다.
ESRGAN_URL = ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
              "realesrgan-ncnn-vulkan-20220424-windows.zip")
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_tool_lock = threading.Lock()


class EnhanceError(RuntimeError):
    pass


def _sharpness(path: Path) -> float:
    from PIL import Image, ImageFilter, ImageStat

    im = Image.open(path).convert("L")
    im.thumbnail((960, 960))
    return ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES)).var[0]


def sharp_frame(video: Path, t: float, duration: float, window: float = 0.8, fps: int = 12) -> dict:
    """t 앞뒤 구간에서 원본 해상도 프레임을 여러 장 뽑아 가장 선명한 것을 돌려준다."""
    start = max(0.0, min(t - window / 2, max(0.0, duration - window)))
    tmp = HQ_DIR / uuid.uuid4().hex[:10]
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            [media._find("ffmpeg"), "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(video),
             "-t", f"{window:.3f}", "-vf", f"fps={fps}", "-q:v", "2", str(tmp / "f_%03d.jpg")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
        frames = sorted(tmp.glob("f_*.jpg"))
        if r.returncode != 0 or not frames:
            raise EnhanceError("원본 영상에서 장면을 뽑지 못했습니다.")
        scores = [(_sharpness(f), i, f) for i, f in enumerate(frames)]
        _, idx, best = max(scores)
        name = f"{tmp.name}_hq.jpg"
        shutil.move(str(best), HQ_DIR / name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    from PIL import Image

    w, h = Image.open(HQ_DIR / name).size
    return {"name": name, "t": round(start + (idx + 0.5) / fps, 3), "width": w, "height": h,
            "candidates": len(frames)}


def _ensure_tool(status_cb=None) -> Path:
    exe = next(TOOL_DIR.rglob("realesrgan-ncnn-vulkan.exe"), None) if TOOL_DIR.exists() else None
    if exe:
        return exe
    if os.name != "nt":
        raise EnhanceError("AI 업스케일은 지금은 Windows에서만 지원합니다.")
    with _tool_lock:
        exe = next(TOOL_DIR.rglob("realesrgan-ncnn-vulkan.exe"), None) if TOOL_DIR.exists() else None
        if exe:
            return exe
        if status_cb:
            status_cb("AI 업스케일 도구를 처음 한 번 내려받는 중 (약 45MB)")
        TOOL_DIR.mkdir(parents=True, exist_ok=True)
        z = TOOL_DIR / "pkg.zip"
        try:
            with httpx.stream("GET", ESRGAN_URL, follow_redirects=True, timeout=180) as r:
                r.raise_for_status()
                with open(z, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            with zipfile.ZipFile(z) as zf:
                for m in zf.namelist():  # 압축 경로 밖으로 나가는 항목 차단
                    if Path(m).is_absolute() or ".." in Path(m).parts:
                        raise EnhanceError("업스케일 도구 압축 파일이 올바르지 않습니다.")
                zf.extractall(TOOL_DIR)
        except EnhanceError:
            raise
        except Exception:
            raise EnhanceError("AI 업스케일 도구를 내려받지 못했습니다. 인터넷 연결을 확인해 주세요.")
        finally:
            z.unlink(missing_ok=True)
        exe = next(TOOL_DIR.rglob("realesrgan-ncnn-vulkan.exe"), None)
        if not exe:
            raise EnhanceError("AI 업스케일 도구를 찾지 못했습니다.")
        return exe


def upscale(src: Path, max_side: int = 2560) -> dict:
    """Real-ESRGAN x4로 키운 뒤 썸네일에 충분한 크기(긴 변 max_side)로 줄여 디테일을 살린다."""
    from PIL import Image

    im = Image.open(src)
    if max(im.size) >= 2400:
        raise EnhanceError("이미 충분히 고해상도인 이미지입니다.")
    exe = _ensure_tool()
    out = HQ_DIR / f"{uuid.uuid4().hex[:10]}_up.png"
    HQ_DIR.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([str(exe), "-i", str(src), "-o", str(out), "-n", "realesrgan-x4plus", "-s", "4"],
                       cwd=str(exe.parent), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=_NO_WINDOW, timeout=600)
    if r.returncode != 0 or not out.exists():
        raise EnhanceError("AI 업스케일에 실패했습니다. 그래픽카드 드라이버(Vulkan 지원)를 확인해 주세요.")
    big = Image.open(out).convert("RGB")
    target = min(max_side, max(im.size) * 2)
    big.thumbnail((target, target), Image.LANCZOS)
    name = out.stem + ".jpg"
    big.save(HQ_DIR / name, "JPEG", quality=95)
    out.unlink(missing_ok=True)
    return {"name": name, "width": big.width, "height": big.height}
