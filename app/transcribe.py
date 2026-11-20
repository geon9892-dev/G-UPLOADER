"""로컬 Whisper(faster-whisper) 음성 인식. PC 사양에 맞춰 모델을 고른다."""
import os
import threading
from pathlib import Path

from . import paths

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

_lock = threading.Lock()
_model = None
_model_key = None
_cuda = None


def _add_cuda_dlls() -> None:
    """pip로 설치한 NVIDIA 라이브러리(cuBLAS, cuDNN) 또는 데이터 폴더의 cuda 폴더를 DLL 경로에 추가."""
    dirs = []
    try:
        import nvidia  # type: ignore

        for base in getattr(nvidia, "__path__", []):
            for sub in ("cublas", "cudnn", "cuda_runtime"):
                dirs.append(Path(base) / sub / "bin")
    except ImportError:
        pass
    dirs.append(paths.DATA_DIR / "cuda")
    for d in dirs:
        if d.is_dir():
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(d))


_add_cuda_dlls()


def has_cuda() -> bool:
    global _cuda
    if _cuda is None:
        try:
            import ctranslate2

            _cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            _cuda = False
    return _cuda


def pick(setting: str):
    cuda = has_cuda()
    name = os.environ.get("GUP_WHISPER_MODEL") or setting
    if not name or name == "auto":
        if cuda:
            name = "large-v3-turbo"
        else:
            name = "medium" if (os.cpu_count() or 4) >= 8 else "small"
    return name, ("cuda" if cuda else "cpu"), ("float16" if cuda else "int8")


def _load(name: str, device: str, compute: str, status_cb):
    global _model, _model_key
    from faster_whisper import WhisperModel

    key = (name, device)
    if _model is not None and _model_key == key:
        return _model
    status_cb(f"Whisper {name} 모델 준비 중 (처음 한 번은 다운로드합니다)")
    _model = WhisperModel(name, device=device, compute_type=compute,
                          download_root=str(paths.MODELS_DIR))
    _model_key = key
    return _model


_GPU_ERR = ("cuda", "cublas", "cudnn", "dll", "library", "gpu", "device")


def transcribe(raw_audio: Path, setting: str, hotwords: str, progress_cb, status_cb) -> list:
    """raw_audio: media.extract_audio가 만든 16kHz 모노 float32 파일."""
    import numpy as np

    audio = np.fromfile(str(raw_audio), dtype=np.float32)
    with _lock:
        name, device, compute = pick(setting)
        try:
            return _run(audio, name, device, compute, hotwords, progress_cb, status_cb)
        except Exception as e:
            if device != "cuda" or not any(k in str(e).lower() for k in _GPU_ERR):
                raise
            # 그래픽카드 라이브러리 문제면 CPU로 다시 시도
            status_cb(f"그래픽카드 사용에 실패해 CPU로 다시 시도합니다 ({type(e).__name__})")
            global _cuda
            _cuda = False
            name, device, compute = pick(setting)
            return _run(audio, name, device, compute, hotwords, progress_cb, status_cb)


def _run(audio, name, device, compute, hotwords, progress_cb, status_cb) -> list:
    model = _load(name, device, compute, status_cb)
    status_cb(f"음성 인식 중 · {name} · {'GPU' if device == 'cuda' else 'CPU'}")
    segments, info = model.transcribe(audio, vad_filter=True, beam_size=5,
                                      hotwords=hotwords or None)
    total = max(info.duration or 0, 1)
    out = []
    for s in segments:
        text = s.text.strip()
        if text:
            out.append({"start": s.start, "end": s.end, "text": text})
        progress_cb(min(s.end / total, 1.0))
    progress_cb(1.0)
    return out
