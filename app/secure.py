"""API 키와 로그인 토큰 보관.

Windows에서는 DPAPI로 암호화해 현재 Windows 사용자만 풀 수 있게 저장한다.
"""
import ctypes
import json
import sys
import threading

from . import paths

_lock = threading.Lock()

if sys.platform == "win32":
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32

    def _dpapi(fn, data: bytes) -> bytes:
        buf = ctypes.create_string_buffer(data, len(data))
        inp = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        out = _Blob()
        if not fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
            code = ctypes.GetLastError()
            raise OSError(f"Windows 암호화(DPAPI) 처리에 실패했습니다 (오류 {code}).")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            _kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))

    def _protect(b: bytes) -> bytes:
        return _dpapi(_crypt32.CryptProtectData, b)

    def _unprotect(b: bytes) -> bytes:
        return _dpapi(_crypt32.CryptUnprotectData, b)
else:  # macOS/Linux: 사용자 홈 폴더 권한에 의존
    def _protect(b: bytes) -> bytes:
        return b

    def _unprotect(b: bytes) -> bytes:
        return b


class SecretsError(OSError):
    pass


def _load(strict: bool = False) -> dict:
    """저장된 키를 읽는다. 파일은 있는데 풀지 못하면 strict일 때 예외를 낸다.

    풀지 못한 채 빈 값으로 덮어쓰면 기존 키가 모두 사라지므로 set()은 strict로 읽는다.
    """
    if not paths.SECRETS_FILE.exists():
        return {}
    try:
        return json.loads(_unprotect(paths.SECRETS_FILE.read_bytes()).decode("utf-8"))
    except Exception as e:
        print(f"[secure] 저장된 키를 읽지 못했습니다: {e}")
        if strict:
            raise SecretsError("저장된 키를 읽지 못해 저장하지 않았습니다. 프로그램을 닫고 다시 열어 주세요.")
        return {}


def get(name: str):
    with _lock:
        return _load().get(name)


def set(name: str, value) -> None:  # noqa: A001
    with _lock:
        data = _load(strict=True)
        if value is None:
            data.pop(name, None)
        else:
            data[name] = value
        paths.SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = paths.SECRETS_FILE.with_suffix(".tmp")
        tmp.write_bytes(_protect(json.dumps(data).encode("utf-8")))
        tmp.replace(paths.SECRETS_FILE)
