"""채널 정체성 파일(마크다운) 읽기와 섹션 해석."""
import re
import shutil

from . import paths

FILE = paths.IDENTITY_DIR / "identity.md"


def ensure() -> None:
    if not FILE.exists():
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tpl = paths.TEMPLATES_DIR / "identity.example.md"
        if tpl.exists():
            shutil.copy(tpl, FILE)
        else:
            FILE.write_text("# 채널 정체성\n", "utf-8")


def read() -> str:
    ensure()
    return FILE.read_text("utf-8-sig")


def write(text: str) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(text, "utf-8")


def section(text: str, keyword: str) -> list:
    """'## ...keyword...' 제목 아래 줄들을 돌려준다(목록 기호 제거, 주석 줄 제외)."""
    lines, inside = [], False
    for raw in text.splitlines():
        if raw.startswith("#"):
            inside = raw.startswith("## ") and keyword in raw
            continue
        if not inside:
            continue
        line = raw.strip()
        if not line or line.startswith(">") or line.startswith("<!--"):
            continue
        lines.append(re.sub(r"^[-*]\s+", "", line))
    return lines


def banned_phrases(text: str) -> list:
    """'절대 쓰지 말 것'에서 따옴표로 감싼 표현만 정확히 검사 대상으로 쓴다."""
    out = []
    for line in section(text, "쓰지 말"):
        for m in re.findall(r'["“”]([^"“”]+)["“”]', line):
            p = m.strip().lstrip("~").strip()
            if p:
                out.append(p)
    return out


def proper_nouns(text: str) -> str:
    words = []
    for line in section(text, "고유명사"):
        words += [w.strip() for w in re.split(r"[,，]", line) if w.strip()]
    return ", ".join(words)


def fixed_footer(text: str) -> str:
    """설명란 고정 문구는 줄바꿈을 그대로 살린다."""
    lines, inside = [], False
    for raw in text.splitlines():
        if raw.startswith("#"):
            inside = raw.startswith("## ") and "고정 문구" in raw
            continue
        if inside and not raw.strip().startswith(">") and not raw.strip().startswith("<!--"):
            lines.append(re.sub(r"^[-*]\s+", "", raw.rstrip()))
    return "\n".join(lines).strip()
