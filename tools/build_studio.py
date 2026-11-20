"""거나두잇 썸네일 스튜디오(원본 HTML)를 G-UPLOADER 안에서 쓰도록 변환한다.

원본: app/static/studio/studio.orig.html  (드라이브 '거나두잇 썸네일 스튜디오/01_실행파일'에서 가져온 v8)
결과: app/static/studio/studio.html

스튜디오를 새 버전으로 바꿀 때는 원본 파일만 교체하고 이 스크립트를 다시 실행한다:
    .venv\\Scripts\\python.exe tools\\build_studio.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "app" / "static" / "studio" / "studio.orig.html"
DST = ROOT / "app" / "static" / "studio" / "studio.html"

HEAD = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Color+Emoji&display=swap">
<style>@font-face{font-family:"Pretendard";src:url("/static/fonts/Pretendard-ExtraBold.otf") format("opentype");font-weight:800;font-display:swap}</style>
<style>
/* G-UPLOADER 안에서: 미리보기를 왼쪽에 고정하고 설정을 오른쪽에 두어 같이 보이게 한다 */
body.gup-embed .wrap{max-width:1720px}
.gup-split{display:grid;gap:16px}
.gup-left,.gup-right{display:grid;gap:12px;align-content:start;min-width:0}
@media (min-width:1000px){
  body.gup-embed .slide.gup-design{grid-template-columns:minmax(0,1fr);overflow:clip}
  body.gup-embed .slide.gup-design .lead{grid-template-columns:minmax(0,1fr) minmax(0,1.7fr);column-gap:34px}
  body.gup-embed .slide.gup-design .lead>*{grid-column:1}
  body.gup-embed .slide.gup-design .lead>.tpl{grid-column:2;grid-row:1/span 8;align-self:start}
  body.gup-embed .slide.gup-design .lead::before,body.gup-embed .slide.gup-design .lead::after{display:none}
  body.gup-embed .slide.gup-design .work{border-left:0;border-top:1px solid rgba(255,255,255,.05)}
  body.gup-embed .gup-split{grid-template-columns:minmax(0,1.3fr) minmax(400px,1fr);align-items:start;gap:22px}
  body.gup-embed .gup-left{position:sticky;top:10px;z-index:2}
  body.gup-embed .gup-left .stage canvas{max-height:calc(100vh - 250px);max-width:100%;width:auto;height:auto}
}
</style>
"""

LAYOUT = r"""
    /* 미리보기(왼쪽, 고정)와 설정(오른쪽) 나란히 배치 */
    {
      document.body.classList.add("gup-embed");
      const stage = $("stage"), work = stage.parentElement, ed = work.querySelector(".editor");
      work.closest(".slide").classList.add("gup-design");
      const split = document.createElement("div"); split.className = "gup-split";
      const left = document.createElement("div"); left.className = "gup-left";
      const right = document.createElement("div"); right.className = "gup-right";
      const fmtRow = work.querySelector(".seg")?.closest(".row");
      [fmtRow, stage, $("save").closest(".row"), $("saveStatus"), $("fallback")].forEach((el) => el && left.append(el));
      right.append(ed);
      split.append(left, right);
      work.prepend(split);
    }
"""

ENHANCE = r"""
  /* ---------- 이모지 글꼴: 그리기 전에 쓰인 이모지 부분만 내려받는다 ---------- */
  var gupEmojiDone = gupEmojiDone || new Set();
  async function gupEmoji() {
    gupEmojiDone = gupEmojiDone || new Set();
    const need = [...ED.layers.map((l) => String(l.text)).join("")].filter((ch) => {
      const cp = ch.codePointAt(0);
      return (cp >= 0x1F000 || (cp >= 0x2600 && cp <= 0x27BF)) && !gupEmojiDone.has(ch);
    });
    if (!need.length) return;
    try { await document.fonts.load('80px "Noto Color Emoji"', need.join("")); } catch {}
    need.forEach((ch) => gupEmojiDone.add(ch));
  }

  /* ---------- 사진 보정·고화질 (tools/build_studio.py가 넣은 부분) ---------- */
  // 배경을 그린 뒤 색온도·선명도·비네팅을 얹는다 (밝기·대비·채도는 ctx.filter로 처리)
  function gupPost(B, W, H) {
    const sharp = B.sharp || 0, warm = B.warm || 0, vig = B.vig || 0;
    if (sharp > 0) {
      const a = sharp / 100 * 0.9;
      const img = ctx.getImageData(0, 0, W, H), s = img.data, o = new Uint8ClampedArray(s), row = W * 4;
      for (let y = 1; y < H - 1; y++) {
        for (let x = 1; x < W - 1; x++) {
          const i = y * row + x * 4;
          for (let c = 0; c < 3; c++) {
            const v = s[i + c] * (1 + 4 * a) - a * (s[i + c - 4] + s[i + c + 4] + s[i + c - row] + s[i + c + row]);
            o[i + c] = v;
          }
        }
      }
      img.data.set(o); ctx.putImageData(img, 0, 0);
    }
    if (warm !== 0) {
      ctx.save(); ctx.globalCompositeOperation = "soft-light";
      ctx.fillStyle = warm > 0 ? `rgba(255,150,40,${warm / 50 * 0.55})` : `rgba(40,130,255,${-warm / 50 * 0.55})`;
      ctx.fillRect(0, 0, W, H); ctx.restore();
    }
    if (vig > 0) {
      const g = ctx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.35, W / 2, H / 2, Math.hypot(W, H) / 2);
      g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(1, `rgba(0,0,0,${vig / 100 * 0.8})`);
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    }
  }
  // 사진 밝기 분포를 보고 노출·대비를 맞춘다
  function gupAuto(B) {
    const src = bgSource(); if (!src) return false;
    const c = document.createElement("canvas"), k = 160 / Math.max(src.width, src.height);
    c.width = Math.max(1, Math.round(src.width * k)); c.height = Math.max(1, Math.round(src.height * k));
    const g = c.getContext("2d"); g.drawImage(src, 0, 0, c.width, c.height);
    const d = g.getImageData(0, 0, c.width, c.height).data, hist = new Array(256).fill(0);
    let n = 0, sum = 0, satSum = 0;
    for (let i = 0; i < d.length; i += 4) {
      const r = d[i], gg = d[i + 1], b = d[i + 2], l = Math.round(0.299 * r + 0.587 * gg + 0.114 * b);
      hist[l]++; n++; sum += l; satSum += Math.max(r, gg, b) - Math.min(r, gg, b);
    }
    const pct = (p) => { let acc = 0; for (let i = 0; i < 256; i++) { acc += hist[i]; if (acc >= n * p) return i; } return 255; };
    const lo = pct(0.02), hi = pct(0.98), mean = sum / n / 255, satAvg = satSum / n / 255;
    B.contrast = Math.round(Math.min(150, Math.max(90, 100 * 0.92 / Math.max(0.3, (hi - lo) / 255))));
    B.bright = Math.round(Math.min(150, Math.max(80, 100 * (0.5 / Math.max(0.15, mean)) ** 0.5)));
    B.sat = Math.round(Math.min(140, Math.max(100, 100 + (0.28 - satAvg) * 120)));
    B.sharp = Math.max(B.sharp || 0, 25);
    return true;
  }
  function gupPresets() { return [
    ["자동 보정", null],
    ["따뜻한 여행", { bright: 104, contrast: 108, sat: 118, warm: 18, sharp: 30, vig: 30 }],
    ["선명하게", { bright: 102, contrast: 115, sat: 112, warm: 0, sharp: 55, vig: 15 }],
    ["차분한 다큐", { bright: 96, contrast: 110, sat: 80, warm: -8, sharp: 25, vig: 45 }],
    ["원래대로", { bright: 100, contrast: 100, sat: 100, warm: 0, sharp: 0, vig: 0, blur: 0 }]
  ]; }
  // 고르고 있는 배경(장면·지금 화면·내 사진)을 새 이미지로 바꾼다
  async function gupReplaceBg(url, newT) {
    const img = new Image(); img.src = url; await img.decode();
    const c = document.createElement("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight;
    c.getContext("2d").drawImage(img, 0, 0);
    if (state.sel >= 0 && state.frames[state.sel]) {
      const f = state.frames[state.sel];
      const small = document.createElement("canvas"), k = 480 / Math.max(c.width, c.height);
      small.width = Math.round(c.width * k); small.height = Math.round(c.height * k);
      small.getContext("2d").drawImage(c, 0, 0, small.width, small.height);
      const blob = await toJpeg(small);
      URL.revokeObjectURL(f.url);
      Object.assign(f, { canvas: c, blob, url: URL.createObjectURL(blob), replaced: true });
      if (newT != null) f.t = newT;
    } else if (state.sel === -2) state.custom = c;
    else if (state.sel === -3 && state.photos[state.photoSel]) state.photos[state.photoSel].canvas = c;
    renderFrames(); redraw();
    return c;
  }
  const gupToken = () => { try { return parent.document.querySelector('meta[name="gup-token"]').content; } catch { return ""; } };
  async function gupApi(path, init) {
    const r = await fetch(path, { ...init, headers: { ...(init.headers || {}), "X-GUP-Token": gupToken() } });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "요청을 처리하지 못했어요.");
    return d;
  }
  let gupJob = null;
  function gupBgTools(body, B) {
    const row = document.createElement("div"); row.className = "row"; row.style.flexWrap = "wrap"; row.style.gap = "6px";
    gupPresets().forEach(([name, vals]) => {
      const b = document.createElement("button"); b.textContent = name;
      b.onclick = () => {
        if (!vals) { if (!gupAuto(B)) return; } else Object.assign(B, vals);
        commitNow(); renderEditor(); redraw();
      };
      row.append(b);
    });
    body.append(section("보정 프리셋", row));
    if (window.parent === window) return;
    const st = document.createElement("p"); st.className = "hint"; st.id = "gupHqStatus";
    const say = (t) => { st.textContent = t; };
    const hq = document.createElement("button"); hq.textContent = "선명한 원본 화질로";
    hq.title = "고른 장면 앞뒤 0.8초를 원본 해상도로 다시 뽑아 가장 선명한 프레임으로 바꿉니다";
    hq.onclick = async () => {
      if (state.sel === -3) return say("내 사진은 원본 화질 추출 대신 AI 업스케일을 쓰세요.");
      const t = state.sel >= 0 && state.frames[state.sel] ? state.frames[state.sel].t : state.sel === -2 ? video.currentTime : null;
      if (t == null || !gupJob) return say("먼저 장면을 고르세요.");
      hq.disabled = true; say("원본에서 가장 선명한 장면을 찾는 중…");
      try {
        const r = await gupApi(`/api/jobs/${gupJob}/hq-frame`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ t }) });
        await gupReplaceBg(r.url, r.t);
        say(`원본 ${r.width}×${r.height}, 프레임 ${r.candidates}장 중 가장 선명한 장면(${fmtPrecise(r.t)})으로 바꿨어요.`);
      } catch (e) { say(e.message); }
      hq.disabled = false;
    };
    const up = document.createElement("button"); up.textContent = "AI 업스케일";
    up.title = "AI로 해상도를 키우고 디테일을 살립니다 (처음 한 번 도구를 내려받아요)";
    up.onclick = async () => {
      const src = bgSource(); if (!src) return say("먼저 장면이나 사진을 고르세요.");
      up.disabled = true; say("AI 업스케일 중… (처음엔 도구를 내려받느라 1분 정도 걸려요)");
      try {
        const blob = await new Promise((r) => { const c = document.createElement("canvas"); c.width = src.width; c.height = src.height; c.getContext("2d").drawImage(src, 0, 0); c.toBlob(r, "image/png"); });
        const fd = new FormData(); fd.append("file", blob, "in.png");
        const r = await gupApi("/api/upscale", { method: "POST", body: fd });
        await gupReplaceBg(r.url, null);
        say(`AI 업스케일 완료: ${src.width}×${src.height} → ${r.width}×${r.height}`);
      } catch (e) { say(e.message); }
      up.disabled = false;
    };
    const row2 = document.createElement("div"); row2.className = "row"; row2.style.gap = "6px"; row2.append(hq, up);
    body.append(section("고화질", row2, st));
  }
"""

BRIDGE = r"""
  /* ---------- G-UPLOADER 연결 (tools/build_studio.py가 넣은 부분) ---------- */
  if (window.parent !== window) {
    const gb = document.createElement("button");
    gb.className = "primary"; gb.id = "gupApply"; gb.textContent = "G-UPLOADER에 적용";
    gb.style.marginLeft = "8px";
    $("save").after(gb);
__LAYOUT__
    gb.onclick = async () => {
      gb.disabled = true;
      await drawThumb(true);
      let blob = null;
      for (let q = 0.92; q >= 0.6; q -= 0.08) {
        blob = await new Promise((r) => cv.toBlob(r, "image/jpeg", q));
        if (blob && blob.size < 1.9 * 1024 * 1024) break;
      }
      redraw();
      gb.disabled = false;
      if (!blob) { setStatus($("saveStatus"), "이미지를 만들지 못했어요.", "err"); return; }
      parent.postMessage({ type: "gup:thumb", blob, fmt: state.fmt }, location.origin);
      setStatus($("saveStatus"), "G-UPLOADER로 보냈어요.", "ok");
    };
    // SAVE PNG: 이 창 안에서는 저장 창을 띄울 수 없어 G-UPLOADER가 대신 파일로 저장한다
    $("save").onclick = async () => {
      await drawThumb(true);
      const blob = await new Promise((r) => cv.toBlob(r, "image/png"));
      redraw();
      if (!blob) { setStatus($("saveStatus"), "이미지를 만들지 못했어요.", "err"); return; }
      const name = `thumbnail_${state.fmt === "long" ? "16x9" : "9x16"}.png`;
      parent.postMessage({ type: "gup:save", blob, name }, location.origin);
      setStatus($("saveStatus"), `${name} 저장했어요 (다운로드 폴더).`, "ok");
    };
    const setMode = (attached) => { gb.textContent = attached ? "G-UPLOADER에 적용" : "JPG로 저장 (업로드용)"; };
    window.addEventListener("message", (e) => {
      if (e.origin !== location.origin || e.source !== parent) return;
      const m = e.data || {};
      if (m.type === "gup:attach") { gupJob = m.job || null; setMode(!!gupJob); return; }
      if (m.type !== "gup:init") return;
      gupJob = m.job || null;
      setMode(!!gupJob);
      if (m.text) {
        applyTemplate("travel");
        const L = ED.layers, t = m.text;
        const put = (i, v) => { if (!L[i]) return; if (v) L[i].text = v; else L[i].show = false; };
        put(0, t.label); put(1, t.sub); put(2, t.line1); put(3, t.line2);
        commitNow(); renderEditor(); redraw();
      }
      if (m.video) loadFile({ url: m.video.url, name: m.video.name, type: "video/mp4" });
    });
    parent.postMessage({ type: "gup:ready" }, location.origin);
  }

"""

PATCHES = [
    # 서버에 있는 영상을 주소로 바로 연다(큰 파일을 다시 올리지 않게)
    ('if (!file || !file.type.startsWith("video/")) {',
     'if (!file || !(file.url || file.type.startsWith("video/"))) {'),
    ("if (video.src) URL.revokeObjectURL(video.src);",
     'if (video.src && video.src.startsWith("blob:")) URL.revokeObjectURL(video.src);'),
    ("video.src = URL.createObjectURL(file);",
     "video.src = file.url || URL.createObjectURL(file);"),
    # 채널 확정 글꼴 Pretendard 추가
    ("const FONTS = [\n",
     'const FONTS = [\n    ["Pretendard", "프리텐다드 ExtraBold", 800, "굵은 고딕"],\n'),
    # 국기 이모지: 윈도우 기본 이모지 글꼴(Segoe UI Emoji)은 국기를 "VN" 같은 글자로 그린다.
    # 구글 Noto Color Emoji를 먼저 쓰게 해서 썸네일과 편집 화면 모두 국기 그림으로 나오게 한다.
    ('"Noto Sans KR", "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif`;',
     '"Noto Sans KR", "Noto Color Emoji", "Apple Color Emoji", "Segoe UI Emoji", sans-serif`;'),
    ('--body: "Noto Sans KR", "Poppins",',
     '--body: "Noto Sans KR", "Noto Color Emoji", "Poppins",'),
    ("    await Promise.all([...new Set(ED.layers.map((l) => l.font))].map(ensureFont));",
     "    await Promise.all([...new Set(ED.layers.map((l) => l.font))].map(ensureFont));\n    await gupEmoji();"),
    # 사진 보정: 기본값·슬라이더·그리기
    ('const bgDefaults = () => ({ zoom: 100, x: 0, y: 0, bright: 100, blur: 0, shadeDir: "left", shadeAmt: 55 });',
     'const bgDefaults = () => ({ zoom: 100, x: 0, y: 0, bright: 100, contrast: 100, sat: 100, warm: 0, sharp: 0, vig: 0, blur: 0, shadeDir: "left", shadeAmt: 55 });'),
    ("bright: ED.bg.bright, blur: ED.bg.blur };",
     "bright: ED.bg.bright, blur: ED.bg.blur, contrast: ED.bg.contrast ?? 100, sat: ED.bg.sat ?? 100, warm: ED.bg.warm ?? 0, sharp: ED.bg.sharp ?? 0, vig: ED.bg.vig ?? 0 };"),
    ('["사진 보정", [["bright", "밝기", 40, 160, 1, "%"], ["blur", "흐림", 0, 20, 1, "px"]]]',
     '["사진 보정", [["bright", "밝기", 40, 160, 1, "%"], ["contrast", "대비", 50, 160, 1, "%"], ["sat", "채도", 0, 200, 1, "%"], '
     '["warm", "색온도", -50, 50, 1, ""], ["sharp", "선명도", 0, 100, 1, "%"], ["vig", "비네팅", 0, 100, 1, "%"], ["blur", "흐림", 0, 20, 1, "px"]]]'),
    ("      if (B.bright !== 100) f.push(`brightness(${B.bright}%)`);",
     "      if (B.bright !== 100) f.push(`brightness(${B.bright}%)`);\n"
     "      if ((B.contrast ?? 100) !== 100) f.push(`contrast(${B.contrast}%)`);\n"
     "      if ((B.sat ?? 100) !== 100) f.push(`saturate(${B.sat}%)`);"),
    ("    ctx.restore();\n    const a = B.shadeAmt / 100;",
     "    ctx.restore();\n    if (src) gupPost(B, W, H);\n    const a = B.shadeAmt / 100;"),
    ("      BG_GROUPS.forEach(([t, specs]) => body.append(section(t, sliderGrid(B, specs))));",
     "      BG_GROUPS.forEach(([t, specs]) => body.append(section(t, sliderGrid(B, specs))));\n      gupBgTools(body, B);"),
    # 연결 코드
    ("  drawThumb(false);\n  if (document.fonts?.ready)",
     ENHANCE + BRIDGE.replace("__LAYOUT__", LAYOUT) + "  drawThumb(false);\n  if (document.fonts?.ready)"),
]


def main() -> None:
    html = SRC.read_text("utf-8")
    for old, new in PATCHES:
        if html.count(old) != 1:
            raise SystemExit(f"원본에서 바꿀 위치를 찾지 못했습니다(스튜디오 구조가 바뀜): {old[:60]!r}")
        html = html.replace(old, new)
    DST.write_text(HEAD + "</head>\n<body>\n" + html + "\n</body>\n</html>\n", "utf-8")
    print(f"만들었습니다: {DST}")


if __name__ == "__main__":
    main()
