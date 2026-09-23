"""RSS로 후보 뉴스 항목을 모은다. 실패하거나 RSS가 없는 소스는 needs_search 목록에 담아
select_and_write.py가 Claude 웹 검색으로 보완하도록 넘긴다.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from sources import AI_KEYWORDS, SOURCES

KST = timezone(timedelta(hours=9))
LOOKBACK_HOURS = 33  # 매일 14:00 KST 실행 기준, 여유를 둔 수집 창
REQUEST_TIMEOUT = 25


@dataclass
class Candidate:
    title: str
    url: str
    source_key: str
    source_name: str
    source_kind: str
    published: str  # ISO 문자열, 알 수 없으면 빈 문자열
    summary: str = ""


def _entry_time(entry) -> datetime | None:
    for field_name in ("published_parsed", "updated_parsed"):
        t = getattr(entry, field_name, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def _matches_keywords(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in AI_KEYWORDS)


def fetch_source(source: dict, cutoff_utc: datetime) -> list[Candidate]:
    if not source.get("rss"):
        return []
    try:
        resp = requests.get(
            source["rss"],
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "ai-news-briefing/1.0 (+github actions)"},
        )
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:  # noqa: BLE001 - 소스 하나 실패해도 전체는 계속 진행
        print(f"[collect] {source['name']} RSS 수집 실패: {exc}", file=sys.stderr)
        return []

    if parsed.bozo and not parsed.entries:
        print(f"[collect] {source['name']} RSS 파싱 실패: {parsed.bozo_exception}", file=sys.stderr)
        return []

    items: list[Candidate] = []
    for entry in parsed.entries:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue

        entry_dt = _entry_time(entry)
        if entry_dt is not None and entry_dt < cutoff_utc:
            continue

        if source.get("keyword_filter") and not _matches_keywords(title):
            continue

        summary = getattr(entry, "summary", "") or ""
        items.append(
            Candidate(
                title=title,
                url=link,
                source_key=source["key"],
                source_name=source["name"],
                source_kind=source["kind"],
                published=entry_dt.isoformat() if entry_dt else "",
                summary=summary[:400],
            )
        )
    return items


def collect_all() -> tuple[list[Candidate], list[dict]]:
    cutoff_utc = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    candidates: list[Candidate] = []
    needs_search: list[dict] = []

    for source in SOURCES:
        if source.get("needs_search") or not source.get("rss"):
            needs_search.append(source)
            continue

        items = fetch_source(source, cutoff_utc)
        print(f"[collect] {source['name']}: {len(items)}건 수집", file=sys.stderr)
        if not items:
            # RSS는 등록돼 있지만 이번 실행에서 비어 있으면(오류 포함) 웹 검색 보완 후보로 넘긴다.
            needs_search.append(source)
        candidates.extend(items)

    return candidates, needs_search


if __name__ == "__main__":
    cands, missing = collect_all()
    print(f"\n총 후보 {len(cands)}건, 웹 검색 보완 필요 소스 {len(missing)}개: "
          f"{[m['name'] for m in missing]}")
