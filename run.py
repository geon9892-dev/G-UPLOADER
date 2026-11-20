"""G-UPLOADER 실행 파일. 로컬 서버를 켜고 브라우저로 화면을 연다."""
import os
import socket
import sys
import threading
import webbrowser

PORT = 8710


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def main() -> None:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    port = int(os.environ.get("GUP_PORT", PORT))
    url = f"http://127.0.0.1:{port}"
    if not _port_free(port):
        # 이미 켜져 있으면 화면만 다시 연다.
        print(f"G-UPLOADER가 이미 실행 중입니다: {url}")
        webbrowser.open(url)
        return

    import uvicorn

    from app import __version__, server

    server.set_port(port)
    server.cleanup_work()
    try:
        server.updater.check()
    except Exception:
        pass

    print("=" * 52)
    print(f"  G-UPLOADER v{__version__}")
    print(f"  화면 주소: {url}")
    print("  이 창을 닫으면 프로그램이 종료됩니다.")
    print("=" * 52)
    if not os.environ.get("GUP_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(server.app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
