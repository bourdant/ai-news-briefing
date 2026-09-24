"""select_and_write.py의 결과 dict를 받아 docs/ 아래에 모바일 반응형 HTML을 생성한다.

- docs/data/YYYY-MM-DD.json : 원본 데이터 (분석용)
- docs/YYYY-MM-DD/index.html : 그날 브리핑 페이지
- docs/index.html : 날짜별 목록 (docs/data/*.json을 스캔해 매번 재생성)
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
DATA_DIR = DOCS_DIR / "data"
WORKER_URL = os.environ.get("CF_WORKER_URL", "").rstrip("/")

CATEGORY_LABEL = {
    "model_release": "🆕 신규 발표",
    "business": "💼 비즈니스",
    "policy": "⚖️ 정책/규제",
    "opensource": "🔓 오픈소스",
    "safety": "🚨 안전성",
    "product": "🛠️ 제품 업데이트",
    "research": "🔬 연구",
    "other": "📌 기타",
}

STYLE_CSS = """
:root{color-scheme:light dark;--bg:#f7f7fb;--card:#ffffff;--text:#1a1a2e;
--muted:#6b6b80;--accent:#5b5bd6;--border:#e6e6ef}
@media (prefers-color-scheme: dark){:root{--bg:#15151f;--card:#1e1e2c;
--text:#f1f1f5;--muted:#9b9bab;--accent:#8888ff;--border:#2c2c3c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",
sans-serif;line-height:1.6;padding-bottom:48px}
.wrap{max-width:640px;margin:0 auto;padding:20px 16px}
header.top{padding:24px 16px 8px;text-align:center}
header.top h1{font-size:1.15rem;margin:0 0 4px}
header.top .date{color:var(--muted);font-size:.9rem}
.one-liner{background:var(--card);border:1px solid var(--border);border-radius:14px;
padding:16px;margin:16px 0;font-weight:600;font-size:1.05rem}
.note{color:var(--muted);font-size:.85rem;margin:8px 0 20px}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;
padding:18px;margin-bottom:16px}
.card .rank{color:var(--accent);font-weight:700;font-size:.8rem}
.card h2{font-size:1.05rem;margin:6px 0 10px}
.card .category{display:inline-block;font-size:.75rem;color:var(--muted);
margin-bottom:10px}
.card .body p{margin:0 0 10px;font-size:.95rem}
.card .metric-note{font-size:.8rem;color:var(--muted);background:var(--bg);
border-radius:8px;padding:8px 10px;margin:10px 0}
.card .sources{font-size:.85rem;margin:10px 0 4px}
.card .sources a{color:var(--accent);text-decoration:none;margin-right:10px}
.reactions{display:flex;gap:10px;margin-top:14px}
.reactions button{flex:1;padding:10px 0;border-radius:10px;border:1px solid var(--border);
background:var(--bg);font-size:1.2rem;cursor:pointer}
.reactions button .count{display:block;font-size:.7rem;color:var(--muted);margin-top:2px}
.reactions button.picked{border-color:var(--accent);background:color-mix(in srgb, var(--accent) 15%, var(--bg))}
.index-list a{display:block;background:var(--card);border:1px solid var(--border);
border-radius:12px;padding:14px 16px;margin-bottom:10px;text-decoration:none;
color:var(--text)}
.index-list a .d{font-size:.8rem;color:var(--muted)}
.index-list a .l{font-weight:600;margin-top:2px}
footer{text-align:center;color:var(--muted);font-size:.8rem;margin-top:24px}
"""

REACTIONS_JS = """
window.WORKER_URL = "__WORKER_URL__";
function pickedKey(date, id){ return "reacted:" + date + ":" + id; }
async function sendReaction(date, id, reaction, btn){
  if(!window.WORKER_URL) return;
  var group = btn.closest(".reactions");
  try{
    var res = await fetch(window.WORKER_URL + "/react", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({date: date, id: id, reaction: reaction})
    });
    var data = await res.json();
    if(data && data.counts){ updateCounts(group, data.counts); }
    try{ localStorage.setItem(pickedKey(date, id), reaction); }catch(e){}
    Array.from(group.querySelectorAll("button")).forEach(function(b){
      b.classList.toggle("picked", b === btn);
    });
  }catch(e){ console.error("reaction send failed", e); }
}
function updateCounts(group, counts){
  Array.from(group.querySelectorAll("button")).forEach(function(b){
    var r = b.getAttribute("data-reaction");
    var span = b.querySelector(".count");
    if(span && counts[r] !== undefined){ span.textContent = counts[r]; }
  });
}
document.addEventListener("DOMContentLoaded", function(){
  document.querySelectorAll(".card").forEach(function(card){
    var date = card.getAttribute("data-date");
    var id = card.getAttribute("data-id");
    var group = card.querySelector(".reactions");
    if(!group) return;
    var picked = null;
    try{ picked = localStorage.getItem(pickedKey(date, id)); }catch(e){}
    if(picked){
      group.querySelectorAll("button").forEach(function(b){
        b.classList.toggle("picked", b.getAttribute("data-reaction") === picked);
      });
    }
    if(window.WORKER_URL){
      fetch(window.WORKER_URL + "/counts?date=" + encodeURIComponent(date) + "&id=" + encodeURIComponent(id))
        .then(function(r){ return r.json(); })
        .then(function(data){ if(data && data.counts) updateCounts(group, data.counts); })
        .catch(function(){});
    }
  });
});
"""


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _render_article(date: str, art: dict) -> str:
    sources_html = " ".join(
        f'<a href="{_esc(s["url"])}" target="_blank" rel="noopener">{_esc(s["name"])} ↗</a>'
        for s in art.get("sources", [])
    )
    body_html = "".join(f"<p>{_esc(p)}</p>" for p in art.get("body", "").split("\n") if p.strip())
    metric_html = (
        f'<div class="metric-note">📊 {_esc(art["metric_note"])}</div>'
        if art.get("metric_note")
        else ""
    )
    category = CATEGORY_LABEL.get(art.get("category", "other"), "📌 기타")
    official = " · 공식 발표" if art.get("is_official_announcement") else ""
    return f"""
<article class="card" data-date="{_esc(date)}" data-id="{_esc(art['id'])}">
  <div class="rank">#{art.get('rank', 0)}</div>
  <h2>{_esc(art['title'])}</h2>
  <div class="category">{category}{official} · {art.get('source_count', len(art.get('sources', [])))}곳에서 확인</div>
  <div class="body">{body_html}</div>
  {metric_html}
  <div class="sources">{sources_html}</div>
  <div class="reactions">
    <button data-reaction="fire" onclick="sendReaction('{_esc(date)}','{_esc(art['id'])}','fire',this)">🔥<span class="count">-</span></button>
    <button data-reaction="meh" onclick="sendReaction('{_esc(date)}','{_esc(art['id'])}','meh',this)">😐<span class="count">-</span></button>
    <button data-reaction="sleep" onclick="sendReaction('{_esc(date)}','{_esc(art['id'])}','sleep',this)">💤<span class="count">-</span></button>
  </div>
</article>"""


def render_day(data: dict) -> Path:
    date = data["date"]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{date}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    day_dir = DOCS_DIR / date
    day_dir.mkdir(parents=True, exist_ok=True)

    articles_html = "".join(_render_article(date, a) for a in data.get("articles", []))
    note_html = (
        f'<div class="note">ℹ️ {_esc(data["selection_note"])}</div>'
        if data.get("selection_note")
        else ""
    )

    page = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(date)} AI 뉴스 브리핑</title>
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<div class="wrap">
<header class="top">
<h1>📩 AI 뉴스 브리핑</h1>
<div class="date">{_esc(date)}</div>
</header>
<div class="one-liner">{_esc(data.get('one_liner', ''))}</div>
{note_html}
{articles_html}
<footer><a href="../index.html">← 전체 브리핑 목록</a></footer>
</div>
<script src="../assets/reactions.js"></script>
</body>
</html>"""
    (day_dir / "index.html").write_text(page, encoding="utf-8")
    return day_dir


def render_index() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 날짜별 브리핑(YYYY-MM-DD.json)만 — last_analysis.json 같은 상태 파일은 제외
    days = sorted(DATA_DIR.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"), reverse=True)
    items = []
    for f in days:
        d = json.loads(f.read_text(encoding="utf-8"))
        date = d["date"]
        one_liner = d.get("one_liner", "")
        items.append(
            f'<a href="./{_esc(date)}/index.html"><div class="d">{_esc(date)}</div>'
            f'<div class="l">{_esc(one_liner)}</div></a>'
        )

    page = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 뉴스 브리핑</title>
<link rel="stylesheet" href="./assets/style.css">
</head>
<body>
<div class="wrap">
<header class="top">
<h1>📩 AI 뉴스 브리핑</h1>
<div class="date">매일 14:00 KST 업데이트</div>
</header>
<div class="index-list">
{''.join(items) if items else '<p>아직 브리핑이 없습니다.</p>'}
</div>
</div>
</body>
</html>"""
    (DOCS_DIR / "index.html").write_text(page, encoding="utf-8")


def write_assets() -> None:
    assets_dir = DOCS_DIR / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    (assets_dir / "reactions.js").write_text(
        REACTIONS_JS.replace("__WORKER_URL__", WORKER_URL), encoding="utf-8"
    )


def render(data: dict) -> Path:
    write_assets()
    day_dir = render_day(data)
    render_index()
    return day_dir


if __name__ == "__main__":
    import sys

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else None
    if payload is None:
        print("사용법: python render_page.py <briefing.json>")
        raise SystemExit(1)
    out = render(payload)
    print(f"렌더링 완료: {out}")
