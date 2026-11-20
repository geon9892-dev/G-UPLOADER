"""YouTube Data API: 계정 연결, 업로드 영상 찾기, 메타데이터·썸네일 적용, 공개."""
import json
import threading

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import secure

SCOPES = ["https://www.googleapis.com/auth/youtube"]
_lock = threading.Lock()
_channel = None


class YTError(RuntimeError):
    pass


def _explain(e: HttpError) -> str:
    try:
        err = json.loads(e.content.decode("utf-8")).get("error", {})
        reason = (err.get("errors") or [{}])[0].get("reason", "")
        message = err.get("message", "")
    except Exception:
        reason, message = "", str(e)
    if reason in ("quotaExceeded", "dailyLimitExceeded"):
        return "오늘 유튜브 API 사용량을 모두 썼습니다. 내일(한국 시간 오후 4~5시 이후) 다시 시도해 주세요."
    if reason == "forbidden" and "thumbnail" in message.lower():
        return "맞춤 썸네일 권한이 없습니다. 유튜브에서 채널 전화번호 인증을 먼저 해 주세요."
    if reason == "videoNotFound":
        return "유튜브에서 영상을 찾을 수 없습니다."
    if reason == "youtubeSignupRequired":
        return "이 구글 계정에 유튜브 채널이 없습니다."
    return f"유튜브 오류: {message or reason or e.resp.status}"


# ---------- 인증 ----------

def save_client(raw: str) -> None:
    try:
        cfg = json.loads(raw)
    except Exception:
        raise YTError("JSON 파일을 읽지 못했습니다.")
    if "installed" not in cfg:
        raise YTError("'데스크톱 앱' 유형의 OAuth 클라이언트 파일이 아닙니다. 설정 안내를 확인해 주세요.")
    secure.set("google_client", raw)


def save_client_id(client_id: str, client_secret: str) -> None:
    """JSON 파일 대신 클라이언트 ID와 보안 비밀번호를 직접 입력한 경우."""
    client_id, client_secret = client_id.strip(), client_secret.strip()
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise YTError("클라이언트 ID 형식이 아닙니다 (….apps.googleusercontent.com 으로 끝나야 합니다).")
    if not client_secret:
        raise YTError("클라이언트 보안 비밀번호를 입력해 주세요.")
    cfg = {"installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }}
    secure.set("google_client", json.dumps(cfg))


def has_client() -> bool:
    return bool(secure.get("google_client"))


def _creds():
    raw = secure.get("google_token")
    if not raw:
        return None
    creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            secure.set("google_token", None)
            raise YTError("유튜브 로그인이 만료되었습니다. 설정에서 다시 연결해 주세요.")
        secure.set("google_token", creds.to_json())
        return creds
    return None


def connected() -> bool:
    try:
        return _creds() is not None
    except YTError:
        return False


def connect() -> dict:
    global _channel
    raw = secure.get("google_client")
    if not raw:
        raise YTError("먼저 OAuth 클라이언트 파일을 등록해 주세요.")
    flow = InstalledAppFlow.from_client_config(json.loads(raw), SCOPES)
    try:
        creds = flow.run_local_server(
            port=0, open_browser=True, timeout_seconds=300, prompt="consent",
            success_message="연결되었습니다. 이 창을 닫고 G-UPLOADER로 돌아가세요.")
    except Exception:
        raise YTError("연결이 취소되었거나 시간이 초과되었습니다. 다시 시도해 주세요.")
    secure.set("google_token", creds.to_json())
    _channel = None
    return channel()


def disconnect() -> None:
    global _channel
    secure.set("google_token", None)
    _channel = None


def _svc():
    creds = _creds()
    if creds is None:
        raise YTError("유튜브 계정이 연결되지 않았습니다. 설정에서 연결해 주세요.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


# ---------- 조회 ----------

def channel() -> dict:
    global _channel
    with _lock:
        if _channel:
            return _channel
        try:
            r = _svc().channels().list(part="snippet,contentDetails", mine=True).execute()
        except HttpError as e:
            raise YTError(_explain(e))
        items = r.get("items") or []
        if not items:
            raise YTError("이 구글 계정에 유튜브 채널이 없습니다.")
        c = items[0]
        _channel = {
            "id": c["id"],
            "title": c["snippet"]["title"],
            "uploads": c["contentDetails"]["relatedPlaylists"]["uploads"],
        }
        return _channel


def cached_channel():
    return _channel


def recent_uploads(limit: int = 30) -> list:
    svc = _svc()
    try:
        pl = svc.playlistItems().list(part="contentDetails", playlistId=channel()["uploads"],
                                      maxResults=min(limit, 50)).execute()
        ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
        if not ids:
            return []
        r = svc.videos().list(part="snippet,status,statistics,fileDetails",
                              id=",".join(ids)).execute()
    except HttpError as e:
        raise YTError(_explain(e))
    out = []
    for v in r.get("items", []):
        out.append({
            "id": v["id"],
            "title": v["snippet"].get("title", ""),
            "published_at": v["snippet"].get("publishedAt", ""),
            "privacy": v["status"].get("privacyStatus", ""),
            "file_name": (v.get("fileDetails") or {}).get("fileName", ""),
            "views": int((v.get("statistics") or {}).get("viewCount", 0) or 0),
            "description": v["snippet"].get("description", ""),
            "tags": v["snippet"].get("tags", []),
        })
    out.sort(key=lambda x: x["published_at"], reverse=True)
    return out


def channel_profile() -> dict:
    """정체성 파일 자동 작성용: 채널 소개와 최근 영상 50개."""
    try:
        r = _svc().channels().list(part="snippet,brandingSettings,statistics", mine=True).execute()
    except HttpError as e:
        raise YTError(_explain(e))
    c = (r.get("items") or [{}])[0]
    return {
        "title": c.get("snippet", {}).get("title", ""),
        "description": c.get("snippet", {}).get("description", ""),
        "keywords": (c.get("brandingSettings", {}).get("channel", {}) or {}).get("keywords", ""),
        "subscribers": (c.get("statistics") or {}).get("subscriberCount", ""),
        "videos": recent_uploads(50),
    }


def match(file_name: str, uploads: list):
    name = file_name.lower()
    hits = [u for u in uploads if u["file_name"] and u["file_name"].lower() == name]
    hits.sort(key=lambda u: u["privacy"] != "private")
    return hits[0] if hits else None


def past_titles(uploads: list, exclude_id: str = "", n: int = 10) -> list:
    pub = [u for u in uploads if u["privacy"] == "public" and u["id"] != exclude_id]
    pub.sort(key=lambda u: u["views"], reverse=True)
    return [{"title": u["title"], "views": u["views"]} for u in pub[:n]]


# ---------- 적용 ----------

_MUTABLE_STATUS = ("privacyStatus", "embeddable", "license", "publicStatsViewable")


def apply(video_id: str, *, title: str, description: str, tags: list, category_id: str,
          language: str, made_for_kids: bool, synthetic: bool, paid: bool, publish_at=None) -> list:
    """메타데이터 적용. 경고 목록을 돌려준다."""
    svc = _svc()
    warnings = []
    try:
        items = svc.videos().list(part="snippet,status", id=video_id).execute().get("items") or []
    except HttpError as e:
        raise YTError(_explain(e))
    if not items:
        raise YTError("유튜브에서 영상을 찾을 수 없습니다.")
    cur = items[0]
    st = cur["status"]

    snippet = {"title": title, "description": description, "tags": tags,
               "categoryId": category_id or cur["snippet"].get("categoryId", "22")}
    if language:
        snippet["defaultLanguage"] = language
        snippet["defaultAudioLanguage"] = language

    status = {k: st[k] for k in _MUTABLE_STATUS if k in st}
    status["selfDeclaredMadeForKids"] = made_for_kids
    status["containsSyntheticMedia"] = synthetic
    if publish_at:
        if st.get("privacyStatus") == "private":
            status["privacyStatus"] = "private"
            status["publishAt"] = publish_at
        else:
            warnings.append("이미 비공개가 아닌 영상이라 예약 공개를 설정하지 않았습니다.")

    body = {"id": video_id, "snippet": snippet, "status": status,
            "paidProductPlacementDetails": {"hasPaidProductPlacement": paid}}
    try:
        svc.videos().update(part="snippet,status,paidProductPlacementDetails", body=body).execute()
    except HttpError as e:
        if "paidProductPlacement" not in str(e.content):
            raise YTError(_explain(e))
        body.pop("paidProductPlacementDetails")
        try:
            svc.videos().update(part="snippet,status", body=body).execute()
        except HttpError as e2:
            raise YTError(_explain(e2))
        if paid:
            warnings.append("유료 프로모션 표시는 API로 설정되지 않았습니다. 유튜브 스튜디오에서 직접 체크해 주세요.")
    return warnings


def upload(path, *, title: str, description: str, tags: list, category_id: str, language: str,
           made_for_kids: bool, synthetic: bool, paid: bool, publish_at=None, progress_cb=None) -> tuple:
    """영상 파일을 비공개로 올리면서 메타데이터를 함께 설정. (video_id, 경고 목록)"""
    svc = _svc()
    warnings = []
    snippet = {"title": title, "description": description, "tags": tags, "categoryId": category_id or "22"}
    if language:
        snippet["defaultLanguage"] = language
        snippet["defaultAudioLanguage"] = language
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": made_for_kids,
              "containsSyntheticMedia": synthetic}
    if publish_at:
        status["publishAt"] = publish_at
    body = {"snippet": snippet, "status": status,
            "paidProductPlacementDetails": {"hasPaidProductPlacement": paid}}

    def _send(part: str, b: dict) -> str:
        media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
        req = svc.videos().insert(part=part, body=b, media_body=media, notifySubscribers=False)
        resp = None
        while resp is None:
            st, resp = req.next_chunk(num_retries=3)
            if st and progress_cb:
                progress_cb(st.progress())
        if progress_cb:
            progress_cb(1.0)
        return resp["id"]

    try:
        vid = _send("snippet,status,paidProductPlacementDetails", body)
    except HttpError as e:
        if "paidProductPlacement" not in str(e.content):
            raise YTError(_explain(e))
        body.pop("paidProductPlacementDetails")
        try:
            vid = _send("snippet,status", body)
        except HttpError as e2:
            raise YTError(_explain(e2))
        if paid:
            warnings.append("유료 프로모션 표시는 API로 설정되지 않았습니다. 유튜브 스튜디오에서 직접 체크해 주세요.")
    return vid, warnings


def set_thumbnail(video_id: str, jpg_path) -> None:
    try:
        _svc().thumbnails().set(videoId=video_id,
                                media_body=MediaFileUpload(str(jpg_path), mimetype="image/jpeg")).execute()
    except HttpError as e:
        raise YTError(_explain(e))


def publish(video_id: str) -> None:
    svc = _svc()
    try:
        items = svc.videos().list(part="status", id=video_id).execute().get("items") or []
        if not items:
            raise YTError("유튜브에서 영상을 찾을 수 없습니다.")
        st = items[0]["status"]
        status = {k: st[k] for k in _MUTABLE_STATUS if k in st}
        for k in ("selfDeclaredMadeForKids", "containsSyntheticMedia"):
            if k in st:
                status[k] = st[k]
        status["privacyStatus"] = "public"
        svc.videos().update(part="status", body={"id": video_id, "status": status}).execute()
    except HttpError as e:
        raise YTError(_explain(e))
