"""ffmpeg로 영상 정보 읽기, 음성·장면 추출, 자막 파일 읽기, 썸네일 준비."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import paths

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_cache: dict = {}


class MediaError(RuntimeError):
    pass


def _find(name: str) -> str:
    if name in _cache:
        return _cache[name]
    exe = name + (".exe" if os.name == "nt" else "")
    candidates = [paths.exe_dir() / "bin" / exe, paths.app_root() / "bin" / exe]
    found = next((str(c) for c in candidates if c.exists()), None) or shutil.which(name)
    if not found and os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        found = next((str(p) for p in base.glob(f"Gyan.FFmpeg*/*/bin/{exe}")), None)
    if not found:
        raise MediaError(f"{name}을(를) 찾을 수 없습니다. ffmpeg를 설치해 주세요.")
    _cache[name] = found
    return found


def _run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", creationflags=_NO_WINDOW)


def probe(path: Path) -> dict:
    out = _run([_find("ffprobe"), "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", str(path)])
    if out.returncode != 0:
        raise MediaError("영상 정보를 읽지 못했습니다. 영상 파일이 맞는지 확인해 주세요.")
    j = json.loads(out.stdout or "{}")
    streams = j.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not v:
        raise MediaError("영상 트랙이 없는 파일입니다.")
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    rot = 0
    if "rotate" in (v.get("tags") or {}):
        rot = int(float(v["tags"]["rotate"]))
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if abs(rot) % 180 == 90:
        w, h = h, w
    dur = float((j.get("format") or {}).get("duration") or v.get("duration") or 0)
    return {
        "duration": dur,
        "width": w,
        "height": h,
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "shorts": dur <= 180 and h >= w,
        "ratio": ratio_label(w, h),
    }


def ratio_label(w: int, h: int) -> str:
    if not w or not h:
        return "알 수 없음"
    r = w / h
    for label, val in (("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0), ("4:3", 4 / 3), ("4:5", 4 / 5)):
        if abs(r - val) < 0.03:
            return label
    return "가로" if r > 1 else "세로"


def fmt_time(sec: float) -> str:
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def extract_audio(path: Path, out_raw: Path) -> Path:
    """16kHz 모노 float32 원시 오디오(Whisper 입력 형식)로 추출."""
    out_raw.parent.mkdir(parents=True, exist_ok=True)
    r = _run([_find("ffmpeg"), "-y", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
              "-ar", "16000", "-f", "f32le", str(out_raw)])
    if r.returncode != 0 or not out_raw.exists():
        raise MediaError("음성을 추출하지 못했습니다.")
    return out_raw


def extract_frames(path: Path, out_dir: Path, duration: float, count: int) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(count):
        t = duration * (i + 0.5) / count
        f = out_dir / f"frame_{i:02d}.jpg"
        r = _run([_find("ffmpeg"), "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path),
                  "-frames:v", "1", "-vf", "scale='min(768,iw)':-2", "-q:v", "4", str(f)])
        if r.returncode == 0 and f.exists():
            frames.append({"time": t, "path": f})
    return frames


_SRT_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def find_subtitle(path: Path):
    """영상 옆에 같은 이름의 .srt가 있으면 음성 인식 대신 사용."""
    srt = path.with_suffix(".srt")
    if not srt.exists():
        return None
    text = srt.read_text("utf-8-sig", errors="replace")
    segs = []
    for block in re.split(r"\n\s*\n", text.strip()):
        m = _SRT_TIME.search(block)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        lines = block[m.end():].strip().splitlines()
        content = " ".join(l.strip() for l in lines if l.strip())
        if content:
            segs.append({"start": start, "end": end, "text": content})
    return segs


def prepare_thumbnail(src: Path, dst: Path, vertical: bool = False) -> Path:
    """롱폼은 1280x720(16:9), 숏폼은 1080x1920(9:16)으로 맞추고 2MB 이하 JPEG로 저장."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    img = ImageOps.fit(img, (1080, 1920) if vertical else (1280, 720), method=Image.LANCZOS)
    for q in (92, 85, 78, 70, 60):
        img.save(dst, "JPEG", quality=q, optimize=True)
        if dst.stat().st_size < 2 * 1024 * 1024:
            break
    return dst
