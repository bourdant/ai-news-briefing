"""2주(14일)마다: Cloudflare Worker에서 반응 데이터를 모아 Claude로 요약하고 카카오톡 전송.
GitHub Actions에서는 매주 실행하되, 이 스크립트가 14일 간격을 자체적으로 체크한다.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from anthropic import Anthropic

KST = timezone(timedelta(hours=9))
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
INTERVAL_DAYS = 14

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
DATA_DIR = DOCS_DIR / "data"
STATE_FILE = DATA_DIR / "last_analysis.json"

CATEGORY_LABEL_KO = {
    "model_release": "신규 모델/기능 발표",
    "business": "비즈니스/투자/주가",
    "policy": "정책/규제",
    "opensource": "오픈소스",
    "safety": "안전성/논란",
    "product": "제품 업데이트",
    "research": "연구",
    "other": "기타",
}


def _load_state() -> dict | None:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return None


def _save_state(date: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"last_run": date}, ensure_ascii=False, indent=2), encoding="utf-8")


def _should_run(today: datetime) -> tuple[bool, str]:
    state = _load_state()
    if not state:
        since = (today - timedelta(days=INTERVAL_DAYS)).strftime("%Y-%m-%d")
        return True, since
    last_run = datetime.strptime(state["last_run"], "%Y-%m-%d").replace(tzinfo=KST)
    if (today - last_run).days < INTERVAL_DAYS:
        return False, ""
    return True, state["last_run"]


def _fetch_reactions(since: str, until: str) -> list[dict]:
    worker_url = os.environ["CF_WORKER_URL"].rstrip("/")
    api_key = os.environ["ANALYSIS_API_KEY"]
    resp = requests.get(
        f"{worker_url}/analysis",
        params={"since": since, "until": until},
        headers={"X-Api-Key": api_key},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["rows"]


def _enrich_with_category(rows: list[dict]) -> list[dict]:
    cache: dict[str, dict] = {}
    enriched = []
    for row in rows:
        date = row["date"]
        if date not in cache:
            f = DATA_DIR / f"{date}.json"
            cache[date] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"articles": []}
        articles = {a["id"]: a for a in cache[date].get("articles", [])}
        art = articles.get(row["id"])
        enriched.append(
            {
                "date": date,
                "id": row["id"],
                "title": art["title"] if art else row["id"],
                "category": art.get("category", "other") if art else "other",
                "counts": row["counts"],
            }
        )
    return enriched


def _summarize_with_claude(enriched: list[dict], since: str, until: str) -> str:
    by_category: dict[str, int] = {}
    top_articles = sorted(enriched, key=lambda r: r["counts"].get("fire", 0), reverse=True)[:8]
    for row in enriched:
        by_category[row["category"]] = by_category.get(row["category"], 0) + row["counts"].get("fire", 0)

    ranked = sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
    ranked_ko = [{"category": CATEGORY_LABEL_KO.get(c, c), "fire_total": n} for c, n in ranked if n > 0]

    client = Anthropic()
    system = (
        "당신은 AI 뉴스 브리핑 구독자의 2주치 반응(🔥/😐/💤 클릭) 데이터를 분석해 "
        "친근한 존댓말 한국어로 짧게 요약하는 역할입니다. 중학생도 이해할 쉬운 말을 씁니다. "
        "카카오톡 메시지 본문으로 쓸 것이므로 전체 200자 이내로, 어떤 종류의 소식에 "
        "🔥가 많았는지 1~2가지를 콕 집어 설명하세요. 마크다운 없이 순수 텍스트만 출력하세요."
    )
    user = (
        f"분석 기간: {since} ~ {until}\n"
        f"카테고리별 🔥 합계: {json.dumps(ranked_ko, ensure_ascii=False)}\n"
        f"🔥가 많았던 기사 상위: "
        f"{json.dumps([{'title': a['title'], 'fire': a['counts'].get('fire', 0)} for a in top_articles], ensure_ascii=False)}"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=500,
        temperature=0.3,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    return text[:200]


def main() -> None:
    today = datetime.now(KST)
    should_run, since = _should_run(today)
    if not should_run:
        print("[analyze_reactions] 아직 14일이 지나지 않아 건너뜁니다.")
        return

    until = today.strftime("%Y-%m-%d")
    print(f"[analyze_reactions] 분석 기간: {since} ~ {until}")

    rows = _fetch_reactions(since, until)
    if not rows:
        print("[analyze_reactions] 이 기간에 반응 데이터가 없습니다. 상태만 갱신합니다.")
        _save_state(until)
        return

    enriched = _enrich_with_category(rows)
    summary = _summarize_with_claude(enriched, since, until)
    print(f"[analyze_reactions] 요약: {summary}")

    from send_kakao import send_text_with_button

    page_base = os.environ["PAGE_BASE_URL"].rstrip("/")
    result = send_text_with_button(summary, "브리핑 목록 보기", page_base)
    print(f"[analyze_reactions] 카카오톡 전송 완료: {result}")

    _save_state(until)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"[analyze_reactions] 실패: {exc}", file=sys.stderr)
        raise
