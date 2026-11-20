"""G-UPLOADER 실행 파일. 로컬 서버를 켜고 프로그램 창(WebView2)으로 화면을 연다.

창을 닫으면 프로그램이 종료된다. GUP_NO_BROWSER=1 이면 창 없이 서버만 켠다(개발용).
"""
import os
import socket
import sys
import threading
import time
import webbrowser

PORT = 8710
TITLE = "G-UPLOADER"


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _setup_output() -> None:
    """콘솔이 없는 창 프로그램이면 출력을 로그 파일로 보낸다(없으면 print·uvicorn 로그가 오류)."""
    if sys.stdout is not None and sys.stderr is not None:
        for s in (sys.stdout, sys.stderr):
            if hasattr(s, "reconfigure"):
                s.reconfigure(encoding="utf-8")
        return
    from app.paths import DATA_DIR

    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    f = open(log_dir / "g-uploader.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f


def _wait_ready(port: int, timeout: float = 30) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if not _port_free(port):
            return True
        time.sleep(0.1)
    return False


SPLASH = """<!doctype html><meta charset="utf-8"><body style="margin:0;height:100vh;display:grid;
place-items:center;background:#0b0b0c;color:#e8e8e8;font:500 15px 'Segoe UI','Malgun Gothic',sans-serif">
<div style="text-align:center"><div style="font-size:30px;letter-spacing:.28em;font-weight:300">G-UPLOADER</div>
<div style="margin-top:14px;color:#8a8a8a">프로그램을 준비하고 있어요…</div></div>"""


def _open_window(url: str, start=None, busy=None) -> bool:
    """프로그램 창을 띄우고 닫힐 때까지 기다린다. 창을 못 띄우면 False.

    start가 있으면 창에 준비 화면을 먼저 보여주고, start()가 True를 돌려주면 url로 넘어간다.
    """
    try:
        import webview
    except Exception as e:
        print(f"프로그램 창을 열 수 없어 브라우저로 엽니다: {e}")
        return False

    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    win = webview.create_window(
        TITLE, url=None if start else url, html=SPLASH if start else None,
        width=1440, height=920, min_size=(900, 640),
        text_select=True, zoomable=True, background_color="#0b0b0c")

    if busy is not None:
        def on_closing():
            try:
                if not busy():
                    return True
            except Exception:
                return True
            return win.create_confirmation_dialog(
                "G-UPLOADER", "분석이나 업로드가 진행 중입니다. 지금 닫으면 작업이 중단됩니다. 닫을까요?")
        win.events.closing += on_closing

    def boot():
        if start is None:
            return
        if start():
            win.load_url(url)
        else:
            win.load_html(SPLASH.replace("프로그램을 준비하고 있어요…",
                                         "시작하지 못했습니다. 로그 파일(%APPDATA%\\G-UPLOADER\\logs)을 확인해 주세요."))

    try:
        webview.start(boot, private_mode=False)
    except Exception as e:
        print(f"프로그램 창 오류, 브라우저로 엽니다: {e}")
        return False
    return True


def main() -> None:
    _setup_output()
    port = int(os.environ.get("GUP_PORT", PORT))
    url = f"http://127.0.0.1:{port}"
    headless = bool(os.environ.get("GUP_NO_BROWSER"))

    if not _port_free(port):
        # 이미 켜져 있으면 화면만 하나 더 연다.
        print(f"G-UPLOADER가 이미 실행 중입니다: {url}")
        if not headless and not _open_window(url):
            webbrowser.open(url)
        return

    state = {}

    def start_server() -> bool:
        """무거운 모듈을 불러오고 서버를 켠다. 창이 뜬 뒤 별도 스레드에서 실행된다."""
        try:
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
            print("=" * 52)
            srv = uvicorn.Server(uvicorn.Config(
                server.app, host="127.0.0.1", port=port, log_level="warning", log_config=None))
            state["server"] = server
            state["thread"] = t = threading.Thread(target=srv.run, daemon=True)
            t.start()
            return _wait_ready(port)
        except Exception:
            import traceback
            traceback.print_exc()
            return False

    def busy() -> bool:
        s = state.get("server")
        return bool(s and s._busy())

    if headless:
        if start_server():
            state["thread"].join()
        return

    if _open_window(url, start=start_server, busy=busy):
        os._exit(0)  # 창을 닫으면 Whisper·업로드 스레드까지 모두 종료

    # 창을 못 띄운 PC: 브라우저로 열고 서버는 계속 켜 둔다.
    if "thread" not in state and not start_server():
        os._exit(1)
    webbrowser.open(url)
    state["thread"].join()


if __name__ == "__main__":
    main()
