"""Claude로 3가지 버전(검색형·클릭형·채널톤형)의 제목·설명·해시태그·태그를 작성하고 점검한다."""
import base64
import json
import re

import anthropic

from . import identity, media, secure, settings

STRATEGIES = {
    "search": "A · 검색형",
    "click": "B · 클릭형",
    "channel": "C · 채널톤형",
}

CATEGORIES = {
    "1": "영화/애니메이션", "2": "자동차", "10": "음악", "15": "동물", "17": "스포츠",
    "19": "여행/이벤트", "20": "게임", "22": "인물/블로그", "23": "코미디",
    "24": "엔터테인먼트", "25": "뉴스/정치", "26": "노하우/스타일", "27": "교육",
    "28": "과학기술",
}

RULES = """너는 유튜브 채널 주인을 대신해 업로드 문구를 쓰는 작가다.
목표는 두 가지다. (1) 유튜브 검색과 추천에서 잘 노출되게 하고, (2) 채널 주인이 직접 쓴 것처럼 읽히게 한다.
아래 [채널 정체성 파일]이 말투, 금지 표현, 시청자, 제목 규칙의 최우선 기준이다. 유튜브 일반 요령과 부딪히면 정체성 파일을 따른다.

유튜브 노출 요령
- 제목은 100자 이하. 사람들이 실제로 검색할 핵심 키워드를 앞쪽에 둔다.
- 설명 첫 두 줄은 검색 결과와 '더보기' 전에 보이므로, 핵심 키워드와 이 영상을 볼 이유를 담는다.
- 해시태그는 3~5개, '#'으로 시작하고 띄어쓰기 없이. 영상 내용과 직접 관련된 것만.
- 태그(tags)는 검색어 변형, 동의어, 띄어쓰기 변형 10~20개. '#' 없이.
- 영상에 실제로 없는 내용을 약속하지 않는다. 오해를 부르는 제목·설명은 유튜브 정책 위반이다.
- 숏폼이면 설명은 1~3줄로 짧게 쓰고, 해시태그에 #Shorts를 넣어도 된다.
- 꺾쇠괄호(< >)는 유튜브가 허용하지 않으니 쓰지 않는다.

AI 티 내지 않기
- 과장 홍보 문구("완벽 가이드", "꿀팁 대방출", "놓치지 마세요" 등), 의미 없는 감탄사, 이모지 남발을 피한다. 정체성 파일이 허용한 표현은 예외.
- [채널 과거 영상]이 있으면 제목 길이, 어미, 띄어쓰기, 기호(|, [ ], ! 등) 쓰는 습관을 그대로 따른다.
- 사람이 쓴 것처럼 문장 길이와 리듬을 자연스럽게 섞는다.

세 가지 버전 (서로 확실히 달라야 한다)
- search(검색형): 검색량이 많을 핵심 키워드를 제목 앞에. 정보가 명확하게.
- click(클릭형): 궁금증, 반전, 감정을 앞세운다. 키워드는 자연스럽게 포함. 낚시는 금지.
- channel(채널톤형): 정체성 파일의 말투와 과거 인기 제목 패턴을 가장 강하게 따른다.

출력 규칙
- description에는 본문만 쓴다. 챕터, 설명란 고정 문구, 해시태그는 넣지 않는다(프로그램이 붙인다).
- 롱폼이고 내용 구간이 뚜렷하면 chapters에 챕터를 쓴다. 첫 챕터는 00:00, 최소 3개, 각 구간 10초 이상. 숏폼이거나 구간이 뚜렷하지 않으면 빈 배열.
- keywords에는 그 버전이 노린 핵심 검색어 2~4개, rationale에는 이 버전을 이렇게 쓴 이유를 한 문장으로.
- category_id는 주어진 목록에서 고르고, language는 영상 언어 코드(예: ko).

썸네일 문구 (thumbnail)
- 썸네일 위에 얹을 짧은 문구다. 제목을 반복하지 말고, 장면과 함께 봤을 때 궁금해지는 말로 쓴다.
- label: 작은 알약 라벨(예: 시리즈·회차 "ep.2", "베트남 기록"). 없으면 빈 문자열.
- sub: 장소나 상황 한 줄(예: "베트남 하노이 🇻🇳"). 12자 안팎. 이모지는 이 줄에 국기 정도만 쓴다.
- line1, line2: 큰 두 줄 제목. 각 8자 안팎, 둘째 줄이 강조(노란색)된다. 채널 말투를 따른다.

공개 표시 판단 (disclosure)
- paid: 영상에 협찬, 광고, 제품 제공, 유료 프로모션 언급이나 정황이 있으면 true. 근거를 paid_reason에 한 문장으로.
- synthetic: 실제처럼 보이는 AI 생성·합성 인물, 장면, 음성이 있으면 true(제목·장면·음성에 AI 제작 정황이 있는 경우 포함). 단순 자막, 색보정, 뷰티 필터는 해당하지 않는다. 근거를 synthetic_reason에 한 문장으로.
- 근거가 없으면 false로 하고 reason은 빈 문자열."""

_VERSION_SCHEMA = {
    "type": "object",
    "properties": {
        "strategy": {"type": "string", "enum": list(STRATEGIES)},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
    },
    "required": ["strategy", "title", "description", "hashtags", "tags", "keywords", "rationale"],
    "additionalProperties": False,
}

_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "category_id": {"type": "string", "enum": list(CATEGORIES)},
        "language": {"type": "string"},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"time": {"type": "string"}, "title": {"type": "string"}},
                "required": ["time", "title"],
                "additionalProperties": False,
            },
        },
        "versions": {"type": "array", "items": _VERSION_SCHEMA},
        "thumbnail": {
            "type": "object",
            "properties": {
                "label": {"type": "string"}, "sub": {"type": "string"},
                "line1": {"type": "string"}, "line2": {"type": "string"},
            },
            "required": ["label", "sub", "line1", "line2"],
            "additionalProperties": False,
        },
        "disclosure": {
            "type": "object",
            "properties": {
                "paid": {"type": "boolean"}, "paid_reason": {"type": "string"},
                "synthetic": {"type": "boolean"}, "synthetic_reason": {"type": "string"},
            },
            "required": ["paid", "paid_reason", "synthetic", "synthetic_reason"],
            "additionalProperties": False,
        },
    },
    "required": ["summary", "category_id", "language", "chapters", "versions", "thumbnail", "disclosure"],
    "additionalProperties": False,
}


class WriterError(RuntimeError):
    pass


def _client() -> anthropic.Anthropic:
    key = secure.get("anthropic_api_key")
    if not key:
        raise WriterError("Claude API 키가 없습니다. 설정에서 키를 입력해 주세요.")
    return anthropic.Anthropic(api_key=key, max_retries=3)


def check_key(key: str, model: str) -> None:
    try:
        anthropic.Anthropic(api_key=key).models.retrieve(model)
    except anthropic.AuthenticationError:
        raise WriterError("API 키가 올바르지 않습니다.")
    except anthropic.NotFoundError:
        raise WriterError(f"이 키로는 {model} 모델을 쓸 수 없습니다.")
    except anthropic.APIConnectionError:
        raise WriterError("인터넷 연결을 확인해 주세요.")


def _call(system: str, content: list, schema) -> dict:
    client = _client()
    model = settings.load()["claude_model"]
    kwargs = dict(
        model=model,
        max_tokens=16000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": content}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
    )
    try:
        try:
            # 안전 분류기가 거절하면 서버가 다른 모델로 자동 재시도(fallback)
            resp = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        except anthropic.BadRequestError as e:
            if "fallback" not in str(e).lower():
                raise
            resp = client.messages.create(**kwargs)
    except anthropic.AuthenticationError:
        raise WriterError("Claude API 키가 올바르지 않습니다. 설정에서 다시 입력해 주세요.")
    except anthropic.PermissionDeniedError:
        raise WriterError("이 API 키로는 해당 모델을 쓸 수 없습니다.")
    except anthropic.RateLimitError:
        raise WriterError("Claude API 사용량 한도에 걸렸습니다. 잠시 후 다시 시도해 주세요.")
    except anthropic.BadRequestError as e:
        msg = str(e)
        if "credit" in msg.lower() or "billing" in msg.lower():
            raise WriterError("Claude API 크레딧이 부족합니다. console.anthropic.com에서 충전해 주세요.")
        raise WriterError(f"Claude 요청 오류: {msg[:300]}")
    except anthropic.APIConnectionError:
        raise WriterError("Claude에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.")
    except anthropic.APIStatusError as e:
        raise WriterError(f"Claude 서버 오류({e.status_code}). 잠시 후 다시 시도해 주세요.")

    if resp.stop_reason == "refusal":
        raise WriterError("AI가 이 영상에 대한 작성을 거절했습니다.")
    if resp.stop_reason == "max_tokens":
        raise WriterError("응답이 너무 길어 잘렸습니다. 다시 시도해 주세요.")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(text)


# ---------- 입력 구성 ----------

def build_context(meta: dict, file_name: str, segments: list, frames: list, past: list) -> dict:
    ident = identity.read()
    system = RULES + "\n\n[채널 정체성 파일]\n" + ident

    content = []
    for f in frames:
        data = base64.standard_b64encode(f["path"].read_bytes()).decode("ascii")
        content.append({"type": "text", "text": f"[장면 {media.fmt_time(f['time'])}]"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})

    if segments:
        transcript = "\n".join(f"[{media.fmt_time(s['start'])}] {s['text']}" for s in segments)
    else:
        transcript = "(말소리가 없거나 인식된 내용이 없습니다. 장면을 보고 판단하세요.)"

    past_txt = "\n".join(f"- {p['title']} (조회수 {p['views']:,})" for p in past) or "(없음)"
    cats = ", ".join(f"{k}={v}" for k, v in CATEGORIES.items())
    info = (
        f"[영상 정보]\n파일명: {file_name}\n형식: {'숏폼' if meta['shorts'] else '롱폼'}"
        f" · 길이 {media.fmt_time(meta['duration'])} · 비율 {meta['ratio']}\n\n"
        f"[음성 내용]\n{transcript}\n\n"
        f"[채널 과거 영상 (조회수 순)]\n{past_txt}\n\n"
        f"[카테고리 목록]\n{cats}"
    )
    content.append({"type": "text", "text": info, "cache_control": {"type": "ephemeral"}})
    return {
        "system": system,
        "content": content,
        "meta": meta,
        "banned": identity.banned_phrases(ident),
        "footer": identity.fixed_footer(ident),
    }


# ---------- 정리·점검 ----------

def _clean(s: str) -> str:
    return s.replace("<", "").replace(">", "").strip()


def _norm_hashtags(tags: list) -> list:
    out, seen = [], set()
    for t in tags:
        t = "#" + re.sub(r"\s+", "", _clean(t)).lstrip("#")
        if len(t) > 1 and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:15]


def _norm_tags(tags: list) -> list:
    out, seen, total = [], set(), 0
    for t in tags:
        t = _clean(t).lstrip("#").strip().replace(",", " ")
        if not t or t.lower() in seen:
            continue
        cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)
        if total + cost > 500:
            break
        seen.add(t.lower())
        out.append(t)
        total += cost
    return out


def _parse_ts(s: str):
    parts = s.strip().split(":")
    if not all(p.isdigit() for p in parts) or not 2 <= len(parts) <= 3:
        return None
    n = [int(p) for p in parts]
    return n[0] * 3600 + n[1] * 60 + n[2] if len(n) == 3 else n[0] * 60 + n[1]


def valid_chapters(chapters: list, duration: float) -> list:
    times = [_parse_ts(c.get("time", "")) for c in chapters]
    if len(chapters) < 3 or None in times or times[0] != 0:
        return []
    for a, b in zip(times, times[1:]):
        if b - a < 10:
            return []
    if duration and duration - times[-1] < 10:
        return []
    return [{"time": media.fmt_time(t), "title": _clean(c["title"])} for t, c in zip(times, chapters)]


def compose_description(body: str, chapters: list, footer: str) -> str:
    parts = [_clean(body)]
    if chapters:
        parts.append("\n".join(f"{c['time']} {c['title']}" for c in chapters))
    if footer:
        parts.append(footer)
    return "\n\n".join(p for p in parts if p)


def problems(v: dict, banned: list) -> list:
    found = []
    text = " ".join([v["title"], v["body"], " ".join(v["hashtags"])])
    for p in banned:
        if p and p in text:
            found.append(f"금지 표현 \"{p}\" 사용")
    if not v["title"]:
        found.append("제목이 비어 있음")
    if len(v["title"]) > 100:
        found.append(f"제목이 100자를 넘음 ({len(v['title'])}자)")
    if len(v["description"].encode("utf-8")) > 5000:
        found.append("설명이 5000바이트를 넘음")
    return found


def finalize(raw: dict, ctx: dict, chapters: list) -> dict:
    v = {
        "strategy": raw["strategy"],
        "label": STRATEGIES.get(raw["strategy"], raw["strategy"]),
        "title": _clean(raw["title"]),
        "body": _clean(raw["description"]),
        "hashtags": _norm_hashtags(raw.get("hashtags", [])),
        "tags": _norm_tags(raw.get("tags", [])),
        "keywords": [k.strip() for k in raw.get("keywords", []) if k.strip()][:4],
        "rationale": raw.get("rationale", "").strip(),
    }
    v["description"] = compose_description(v["body"], [] if ctx["meta"]["shorts"] else chapters, ctx["footer"])
    v["problems"] = problems(v, ctx["banned"])
    return v


# ---------- 생성 ----------

def generate(ctx: dict) -> dict:
    req = ctx["content"] + [{"type": "text", "text": "위 영상에 대해 search, click, channel 세 버전을 각각 하나씩 작성해 주세요."}]
    data = _call(ctx["system"], req, _RESULT_SCHEMA)

    chapters = valid_chapters(data.get("chapters", []), ctx["meta"]["duration"])
    by_strategy = {}
    for raw in data.get("versions", []):
        by_strategy.setdefault(raw.get("strategy"), raw)
    missing = [s for s in STRATEGIES if s not in by_strategy]
    if missing:
        raise WriterError("AI가 세 가지 버전을 모두 만들지 못했습니다. 다시 시도해 주세요.")
    ctx["chapters"] = chapters
    return {
        "summary": data.get("summary", ""),
        "category_id": data.get("category_id", "22"),
        "language": (data.get("language") or "ko")[:5],
        "chapters": chapters,
        "thumbnail": data.get("thumbnail") or {},
        "disclosure": data.get("disclosure") or {"paid": False, "paid_reason": "", "synthetic": False, "synthetic_reason": ""},
        "versions": [finalize(by_strategy[s], ctx, chapters) for s in STRATEGIES],
    }


def rewrite(ctx: dict, version: dict, instruction: str = "", issues: list = None) -> dict:
    ask = [f"[기존 {version['label']} 버전]",
           json.dumps({k: version[k] for k in ("title", "body", "hashtags", "tags")}, ensure_ascii=False)]
    if issues:
        ask.append("[고쳐야 할 문제]\n" + "\n".join(f"- {i}" for i in issues))
    if instruction:
        ask.append(f"[요청]\n{instruction}")
    ask.append(f"같은 전략({version['strategy']})으로 새 버전 하나를 작성해 주세요. 기존과 확실히 다르게 써도 됩니다."
               if not issues else "문제를 고친 버전 하나를 작성해 주세요. 나머지 장점은 유지하세요.")
    req = ctx["content"] + [{"type": "text", "text": "\n\n".join(ask)}]
    raw = _call(ctx["system"], req, _VERSION_SCHEMA)
    raw["strategy"] = version["strategy"]
    return finalize(raw, ctx, ctx.get("chapters", []))


IDENTITY_RULES = """너는 유튜브 채널 분석가다. 채널 주인이 직접 쓴 제목과 설명을 읽고, 이 채널의 정체성 파일을 작성한다.
이 파일은 나중에 AI가 이 채널 주인처럼 제목·설명을 쓰는 기준이 된다. 그러니 일반론이 아니라 이 채널에서 실제로 관찰된 습관을 구체적으로 적는다.

반드시 지킬 것
- [템플릿]의 섹션 제목(## 채널 소개, ## 말투, ## 절대 쓰지 말 것, ## 제목 규칙, ## 잘된 제목 예시, ## 고유명사, ## 설명란 고정 문구)을 그대로 쓴다.
- 말투: 존댓말/반말, 문장 길이, 자주 쓰는 어미와 표현, 감정 표현 방식을 실제 예를 들어 쓴다.
- 절대 쓰지 말 것: 이 채널이 쓰지 않는 상투적 표현을 "따옴표"로 감싸 나열한다(프로그램이 자동 검사한다). 이모지·기호 습관도 적는다.
- 제목 규칙: 실제 제목들의 평균 길이, 구분자(| 등) 사용, 키워드 위치, 숫자·괄호 사용 습관을 관찰해 적는다.
- 잘된 제목 예시: 조회수 높은 제목 5~10개를 그대로 옮긴다.
- 고유명사: 채널명, 출연자, 반복되는 장소·브랜드·용어를 쉼표로.
- 설명란 고정 문구: 여러 영상 설명 끝에 반복되는 문구(링크, 문의처 등)가 있으면 그대로 옮기고, 없으면 섹션 제목만 남기고 비워 둔다.
- 관찰할 수 없는 내용은 지어내지 말고 생략한다.
- ">"로 시작하는 안내문 줄은 템플릿처럼 섹션 아래 한 줄씩 남겨도 된다."""

_IDENTITY_SCHEMA = {
    "type": "object",
    "properties": {"markdown": {"type": "string"}},
    "required": ["markdown"],
    "additionalProperties": False,
}


def build_identity(profile: dict, template: str) -> str:
    lines = [f"[채널] {profile['title']} (구독자 {profile.get('subscribers') or '?'})",
             f"[채널 소개]\n{profile.get('description') or '(없음)'}",
             f"[채널 키워드] {profile.get('keywords') or '(없음)'}",
             "[최근 영상 (최신순)]"]
    for v in profile["videos"]:
        if v["privacy"] != "public":
            continue
        desc = v["description"].strip().replace("\r", "")
        lines.append(f"\n### {v['title']}\n조회수 {v['views']:,} · 태그: {', '.join(v['tags'][:15]) or '없음'}\n{desc[:1500]}")
    if len(lines) <= 4:
        raise WriterError("분석할 공개 영상이 없습니다. 정체성 파일을 직접 작성해 주세요.")
    content = [{"type": "text", "text": "[템플릿]\n" + template},
               {"type": "text", "text": "\n".join(lines) + "\n\n위 채널의 정체성 파일을 마크다운으로 작성해 주세요."}]
    md = _call(IDENTITY_RULES, content, _IDENTITY_SCHEMA)["markdown"].strip()
    if "## " not in md:
        raise WriterError("정체성 파일을 만들지 못했습니다. 다시 시도해 주세요.")
    return md + "\n"


def self_check(ctx: dict, result: dict) -> None:
    """금지 표현·길이 문제가 있는 버전은 한 번 고쳐 쓴다."""
    for i, v in enumerate(result["versions"]):
        if v["problems"]:
            fixed = rewrite(ctx, v, issues=v["problems"])
            if len(fixed["problems"]) <= len(v["problems"]):
                result["versions"][i] = fixed
