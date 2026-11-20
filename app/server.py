"""로컬 웹 서버. 브라우저 화면(app/static)과 API를 제공한다."""
import json
import re
import secrets as pysecrets
import shutil
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, enhance, identity, media, paths, secure, settings, transcribe, updater, writer, youtube

TOKEN = pysecrets.token_urlsafe(24)
BUILD = str(int(time.time()))  # 실행할 때마다 바뀌어 브라우저가 옛 화면 파일을 쓰지 않게 한다
ALLOWED_HOSTS: set = set()

paths.ensure_dirs()
identity.ensure()

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(paths.STATIC_DIR)), name="static")

KNOWN_ERRORS = (writer.WriterError, youtube.YTError, media.MediaError, updater.UpdateError,
                enhance.EnhanceError)


def set_port(port: int) -> None:
    ALLOWED_HOSTS.update({f"127.0.0.1:{port}", f"localhost:{port}"})


@app.middleware("http")
async def guard(request: Request, call_next):
    # 다른 웹사이트가 이 로컬 서버를 몰래 호출하지 못하게 막는다.
    if ALLOWED_HOSTS and request.headers.get("host", "") not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    if request.url.path.startswith("/api/") and request.headers.get("x-gup-token") != TOKEN:
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    return await call_next(request)


async def _known_error(request: Request, exc: Exception):
    return JSONResponse({"detail": str(exc)}, status_code=400)


for _err in KNOWN_ERRORS:
    app.add_exception_handler(_err, _known_error)


def _busy() -> bool:
    return (any(j.status == "running" for j in JOBS.values())
            or any(t["status"] == "running" for t in TASKS.values()))


def fail(msg: str):
    raise HTTPException(status_code=400, detail=msg)


@app.get("/", response_class=HTMLResponse)
def index():
    html = (paths.STATIC_DIR / "index.html").read_text("utf-8")
    return (html.replace("__GUP_TOKEN__", TOKEN).replace("__GUP_VERSION__", __version__)
            .replace("__GUP_BUILD__", BUILD))


# ---------- 상태·설정 ----------

@app.get("/api/state")
def state():
    cfg = settings.load()
    ch = None
    if youtube.connected():
        try:
            ch = youtube.channel()
        except youtube.YTError:
            ch = None
    name, device, _ = transcribe.pick(cfg["whisper_model"])
    return {
        "version": __version__,
        "has_claude": bool(secure.get("anthropic_api_key")),
        "has_google_client": youtube.has_client(),
        "channel": ch and {"title": ch["title"], "id": ch["id"]},
        "settings": cfg,
        "whisper": {"model": name, "device": device},
        "update": updater.cached(),
        "busy": _busy(),
    }


class ClaudeKey(BaseModel):
    key: str
    model: str = ""


@app.post("/api/settings/claude")
def set_claude(body: ClaudeKey):
    model = body.model or settings.load()["claude_model"]
    key = body.key.strip()
    if not key:
        fail("API 키를 입력해 주세요.")
    writer.check_key(key, model)
    secure.set("anthropic_api_key", key)
    settings.update({"claude_model": model})
    return {"ok": True}


@app.post("/api/settings")
async def set_settings(request: Request):
    patch = await request.json()
    allowed = {k: patch[k] for k in ("claude_model", "whisper_model", "defaults") if k in patch}
    return settings.update(allowed)


@app.post("/api/google/client")
async def google_client(file: UploadFile = File(...)):
    raw = (await file.read()).decode("utf-8", errors="replace")
    youtube.save_client(raw)
    return {"ok": True}


class ClientId(BaseModel):
    client_id: str
    client_secret: str


@app.post("/api/google/client-id")
def google_client_id(body: ClientId):
    youtube.save_client_id(body.client_id, body.client_secret)
    return {"ok": True}


@app.post("/api/google/connect")
def google_connect():
    ch = youtube.connect()
    return {"channel": {"title": ch["title"], "id": ch["id"]}}


@app.post("/api/google/disconnect")
def google_disconnect():
    youtube.disconnect()
    return {"ok": True}


@app.get("/api/identity")
def get_identity():
    return {"text": identity.read(), "path": str(identity.FILE)}


class IdentityText(BaseModel):
    text: str


@app.post("/api/identity")
def save_identity(body: IdentityText):
    identity.write(body.text)
    return {"ok": True}


@app.post("/api/identity/generate")
def generate_identity():
    """내 채널의 제목·설명을 분석해 정체성 파일 초안을 만든다(저장은 사용자가)."""
    tpl = (paths.TEMPLATES_DIR / "identity.example.md").read_text("utf-8")
    return {"text": writer.build_identity(youtube.channel_profile(), tpl)}


# ---------- 영상 선택 ----------

_pick_lock = threading.Lock()


@app.post("/api/pick")
def pick_file():
    """Windows 파일 선택 창을 띄워 실제 파일 경로를 받는다(복사 없이 원본 분석)."""
    with _pick_lock:
        import tkinter
        from tkinter import filedialog

        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            p = filedialog.askopenfilename(
                parent=root, title="G-UPLOADER · 영상 파일 선택",
                filetypes=[("영상 파일", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.flv"), ("모든 파일", "*.*")])
        finally:
            root.destroy()
    return {"path": p or ""}


@app.post("/api/upload-video")
async def upload_video(file: UploadFile = File(...)):
    """끌어다 놓기로 들어온 파일은 작업 폴더에 받아 둔다(파일명 유지)."""
    d = paths.WORK_DIR / "uploads" / uuid.uuid4().hex[:8]
    d.mkdir(parents=True, exist_ok=True)
    dst = d / Path(file.filename or "video.mp4").name
    with open(dst, "wb") as f:
        while chunk := await file.read(8 << 20):
            f.write(chunk)
    return {"path": str(dst)}


# ---------- 작업 ----------

STEPS = [
    ("format", "형식 판별"),
    ("stt", "음성 인식 (로컬 Whisper)"),
    ("frames", "장면 분석"),
    ("channel", "채널 확인"),
    ("write", "3가지 버전 작성"),
    ("check", "AI 말투 점검"),
]


class Job:
    def __init__(self, path: Path):
        self.id = uuid.uuid4().hex[:12]
        self.path = path
        self.status = "running"
        self.error = None
        self.steps = [{"key": k, "label": l, "state": "wait"} for k, l in STEPS]
        self.progress = None
        self.note = ""
        self.warnings = []
        self.meta = None
        self.video = None
        self.uploads = []
        self.result = None
        self.ctx = None
        self.work = paths.WORK_DIR / self.id

    def step(self, key: str):
        for s in self.steps:
            if s["state"] == "run":
                s["state"] = "done"
            if s["key"] == key:
                s["state"] = "run"
        self.progress, self.note = None, ""

    def to_dict(self):
        return {
            "id": self.id, "status": self.status, "error": self.error, "steps": self.steps,
            "progress": self.progress, "note": self.note, "warnings": self.warnings,
            "file_name": self.path.name, "meta": self.meta, "video": self.video,
            "uploads": [{k: u[k] for k in ("id", "title", "privacy", "published_at", "file_name")}
                        for u in self.uploads],
            "result": self.result,
        }


JOBS: dict = {}


def _run_job(job: Job):
    try:
        cfg = settings.load()
        ident = identity.read()

        job.step("format")
        meta = media.probe(job.path)
        job.meta = meta

        job.step("stt")
        segments = media.find_subtitle(job.path)
        if segments is not None:
            job.note = "같은 이름의 자막 파일(.srt)을 사용했습니다"
        elif not meta["has_audio"]:
            segments = []
            job.note = "음성 트랙이 없습니다"
        else:
            wav = media.extract_audio(job.path, job.work / "audio.f32")
            segments = transcribe.transcribe(
                wav, cfg["whisper_model"], identity.proper_nouns(ident),
                progress_cb=lambda p: setattr(job, "progress", round(p, 3)),
                status_cb=lambda s: setattr(job, "note", s))
            wav.unlink(missing_ok=True)

        job.step("frames")
        count = 5 if meta["shorts"] else 8
        frames = media.extract_frames(job.path, job.work / "frames", meta["duration"], count)

        job.step("channel")
        past = []
        if youtube.connected():
            try:
                job.uploads = youtube.recent_uploads()
                job.video = youtube.match(job.path.name, job.uploads)
                past = youtube.past_titles(job.uploads, job.video["id"] if job.video else "")
                if not job.video:
                    job.warnings.append("같은 파일명으로 올라간 영상을 찾지 못했습니다. 아래에서 직접 골라 주세요.")
            except youtube.YTError as e:
                job.warnings.append(str(e))
        else:
            job.note = "유튜브 미연결 · 건너뜀"

        job.step("write")
        job.ctx = writer.build_context(meta, job.path.name, segments, frames, past)
        result = writer.generate(job.ctx)
        result["transcript_chars"] = sum(len(s["text"]) for s in segments)

        job.step("check")
        writer.self_check(job.ctx, result)

        job.step("")
        job.result = result
        job.status = "done"
    except KNOWN_ERRORS as e:
        job.status, job.error = "error", str(e)
    except Exception as e:  # 예상 못 한 오류는 로그에 남긴다
        traceback.print_exc()
        job.status, job.error = "error", f"예상하지 못한 오류가 발생했습니다: {type(e).__name__}: {e}"
    finally:
        for s in job.steps:
            if s["state"] == "run":
                s["state"] = "fail" if job.status == "error" else "done"


class NewJob(BaseModel):
    path: str


@app.post("/api/jobs")
def new_job(body: NewJob):
    p = Path(body.path)
    if not p.is_file():
        fail("파일을 찾을 수 없습니다.")
    if any(j.status == "running" for j in JOBS.values()):
        fail("이미 분석 중인 영상이 있습니다.")
    job = Job(p)
    JOBS[job.id] = job
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    return {"id": job.id}


def _job(job_id: str) -> Job:
    job = JOBS.get(job_id)
    if not job:
        fail("작업을 찾을 수 없습니다. 영상을 다시 넣어 주세요.")
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return _job(job_id).to_dict()


class Rewrite(BaseModel):
    strategy: str
    instruction: str = ""


@app.post("/api/jobs/{job_id}/rewrite")
def rewrite(job_id: str, body: Rewrite):
    job = _job(job_id)
    if not job.result:
        fail("아직 작성이 끝나지 않았습니다.")
    idx = next((i for i, v in enumerate(job.result["versions"]) if v["strategy"] == body.strategy), None)
    if idx is None:
        fail("버전을 찾을 수 없습니다.")
    v = writer.rewrite(job.ctx, job.result["versions"][idx], instruction=body.instruction)
    job.result["versions"][idx] = v
    return v


@app.get("/media/{job_id}")
def job_media(job_id: str):
    """썸네일 스튜디오가 분석한 원본 영상을 바로 열 수 있게 제공(구간 요청 지원, 이 PC 안에서만)."""
    job = JOBS.get(job_id)
    if not job or not job.path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(job.path, media_type="video/mp4")


class HqFrame(BaseModel):
    t: float


@app.post("/api/jobs/{job_id}/hq-frame")
def hq_frame(job_id: str, body: HqFrame):
    job = _job(job_id)
    dur = job.meta["duration"] if job.meta else 0
    r = enhance.sharp_frame(job.path, max(0.0, body.t), dur)
    r["url"] = "/tmb/" + r["name"]
    return r


@app.post("/api/upscale")
async def upscale_image(file: UploadFile = File(...)):
    enhance.HQ_DIR.mkdir(parents=True, exist_ok=True)
    src = enhance.HQ_DIR / f"{uuid.uuid4().hex[:10]}_in.png"
    src.write_bytes(await file.read())
    try:
        import anyio

        r = await anyio.to_thread.run_sync(enhance.upscale, src)
    finally:
        src.unlink(missing_ok=True)
    r["url"] = "/tmb/" + r["name"]
    return r


@app.get("/tmb/{name}")
def hq_file(name: str):
    if not re.fullmatch(r"[0-9a-f]{10}_(hq|up)\.jpg", name):
        raise HTTPException(status_code=404)
    p = enhance.HQ_DIR / name
    if not p.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(p, media_type="image/jpeg")


@app.get("/api/uploads")
def uploads():
    return youtube.recent_uploads()


@app.post("/api/thumbnail")
async def thumbnail(file: UploadFile = File(...), vertical: bool = False):
    d = paths.WORK_DIR / "thumbs"
    d.mkdir(parents=True, exist_ok=True)
    src = d / f"{uuid.uuid4().hex[:8]}_src"
    src.write_bytes(await file.read())
    try:
        dst = media.prepare_thumbnail(src, src.with_name(src.stem + ".jpg"), vertical=vertical)
    except Exception:
        fail("이미지를 읽지 못했습니다.")
    finally:
        src.unlink(missing_ok=True)
    return {"id": dst.name}


class Apply(BaseModel):
    job_id: str
    video_id: str
    title: str
    description: str
    hashtags: list
    tags: list
    category_id: str
    language: str = "ko"
    made_for_kids: bool = False
    synthetic: bool = False
    paid: bool = False
    publish_at: str | None = None
    thumbnail_id: str | None = None
    picked: dict = {}
    edited: bool = False


NEW_VIDEO = "__new__"
TASKS: dict = {}


def _run_apply(task: dict, body: Apply, title: str, desc: str):
    try:
        job = JOBS.get(body.job_id)
        meta = dict(title=title, description=desc, tags=body.tags, category_id=body.category_id,
                    language=body.language, made_for_kids=body.made_for_kids,
                    synthetic=body.synthetic, paid=body.paid, publish_at=body.publish_at)
        if body.video_id == NEW_VIDEO:
            if not job:
                raise youtube.YTError("분석한 영상 정보가 없습니다. 영상을 다시 넣어 주세요.")
            task["stage"] = "업로드 중"
            video_id, warnings = youtube.upload(
                job.path, progress_cb=lambda p: task.update(progress=round(p, 3)), **meta)
        else:
            task["stage"] = "세팅 적용 중"
            video_id = body.video_id
            warnings = youtube.apply(video_id, **meta)
        task["video_id"] = video_id

        if body.thumbnail_id:
            thumb = paths.WORK_DIR / "thumbs" / Path(body.thumbnail_id).name
            if thumb.exists():
                task["stage"] = "썸네일 적용 중"
                try:
                    youtube.set_thumbnail(video_id, thumb)
                except youtube.YTError as e:
                    warnings.append(str(e) + " (숏폼은 유튜브 처리가 끝난 뒤 [다시 적용]하면 됩니다)")

        record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "file_name": job.path.name if job else "",
            "video_id": video_id,
            "uploaded": body.video_id == NEW_VIDEO,
            "picked": body.picked,
            "edited": body.edited,
            "final": {"title": title, "description": desc, "tags": body.tags},
            "versions": job.result["versions"] if job and job.result else [],
        }
        (paths.HISTORY_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}_{video_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), "utf-8")
        task.update(status="done", warnings=warnings)
    except KNOWN_ERRORS as e:
        task.update(status="error", error=str(e))
    except Exception as e:
        traceback.print_exc()
        task.update(status="error", error=f"예상하지 못한 오류: {type(e).__name__}: {e}")


@app.post("/api/apply")
def apply(body: Apply):
    title = body.title.strip()
    if not title:
        fail("제목이 비어 있습니다.")
    hashtags = " ".join(h for h in body.hashtags if h)
    desc = body.description.strip()
    if hashtags:
        desc = f"{desc}\n\n{hashtags}" if desc else hashtags
    if len(title) > 100:
        fail(f"제목이 100자를 넘습니다 ({len(title)}자).")
    if len(desc.encode("utf-8")) > 5000:
        fail("설명이 5000바이트를 넘습니다.")
    if any(t["status"] == "running" for t in TASKS.values()):
        fail("이미 업로드·적용 중입니다.")
    task = {"id": uuid.uuid4().hex[:10], "status": "running", "stage": "준비 중", "progress": None,
            "video_id": None, "warnings": [], "error": None}
    TASKS[task["id"]] = task
    threading.Thread(target=_run_apply, args=(task, body, title, desc), daemon=True).start()
    return {"task": task["id"]}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    t = TASKS.get(task_id)
    if not t:
        fail("작업을 찾을 수 없습니다.")
    return t


class Publish(BaseModel):
    video_id: str


@app.post("/api/publish")
def publish(body: Publish):
    youtube.publish(body.video_id)
    return {"ok": True}


# ---------- 업데이트 ----------

@app.get("/api/update/check")
def update_check():
    return updater.check()


@app.post("/api/update/install")
def update_install():
    if _busy():
        fail("분석·업로드가 끝난 뒤에 업데이트해 주세요.")
    updater.install()
    return {"ok": True}


def cleanup_work(max_age_days: int = 3) -> None:
    """오래된 작업 파일 정리(분석용 임시 파일만)."""
    cutoff = time.time() - max_age_days * 86400
    for d in paths.WORK_DIR.glob("*"):
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass
