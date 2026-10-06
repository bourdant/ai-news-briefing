"""주요 언론사 섹션 페이지의 '배치 순서'(편집자가 위에 건 순서)를 읽어 중요도 신호로 쓴다.

RSS는 시간순이라 중요도를 알 수 없으므로, 섹션 페이지를 직접 받아 위에서부터의 순서를 순위로 삼는다.
사이트 개편 등으로 읽기에 실패하면 그 사이트는 건너뛴다 (RSS 후보는 그대로 남는다).
"""
from __future__ import annotations

import html
import re
import sys

import requests

from sources import AI_KEYWORDS

TOP_N = 15  # 사이트별로 Claude에게 넘길 상위 항목 수
MIN_ITEMS = 3  # 이보다 적게 읽히면 페이지 구조가 바뀐 것으로 보고 건너뜀
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}

# 섹션 전체가 AI 기사는 아니므로 제목으로 거른다
EXTRA_KEYWORDS = [
    "nvidia", "chatbot", "data center", "superintelligence", "deepfake", "xai", "grok",
    "mistral", "copilot", "meta ai", "chip", "semiconductor",
    "엔비디아", "챗봇", "데이터센터", "반도체", "hbm", "딥페이크", "에이전트", "llm",
]


def _clean(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", s)).split())


def _is_ai(title: str) -> bool:
    t = title.lower()
    if re.search(r"\bai\b|a\.i\.", t):
        return True
    return any(k in t for k in AI_KEYWORDS + EXTRA_KEYWORDS if k != "ai")


def _get(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    return resp.text


def _dedupe(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen, out = set(), []
    for title, url in rows:
        if title and url not in seen and title not in seen:
            seen.update({title, url})
            out.append((title, url))
    return out


def _nbc() -> list[tuple[str, str]]:
    x = _get("https://www.nbcnews.com/artificial-intelligence")
    rows = re.findall(r'<h2[^>]*>.*?<a[^>]*href="(https://www\.nbcnews\.com/[^"]+-rcna\d+)"[^>]*>(.*?)</a>', x, re.S)
    # 사진 출처 문구("Aaron Schwartz / Getty")가 제목처럼 잡히는 것 제외
    return _dedupe([(_clean(t), u) for u, t in rows if not re.search(r" / |Getty|AP Photo", _clean(t))])


def _abc() -> list[tuple[str, str]]:
    x = _get("https://abcnews.go.com/Technology")
    x = x[x.find('"section":{"header"'):]  # 상단 메뉴·사이드바 링크 제외
    rows = re.findall(r'"headline":"((?:[^"\\]|\\.)*)".*?"link":"([^"]+)"', x)
    return _dedupe([(_clean(t.encode().decode("unicode_escape", "ignore") if "\\u" in t else t), u)
                    for t, u in rows if "/story" in u or "/wireStory" in u])


def _techmeme() -> list[tuple[str, str]]:
    x = _get("https://www.techmeme.com/")
    rows, seen_clusters = [], set()
    for m in re.finditer(r'CLASS="item" ID="(\d+)i[^"]*">.*?CLASS="ourh" HREF="([^"]+)">(.*?)</A>', x, re.S):
        cluster = m.group(1)
        if cluster in seen_clusters:  # 클러스터마다 대표(첫) 기사만
            continue
        seen_clusters.add(cluster)
        rows.append((_clean(m.group(3)), m.group(2)))
    return _dedupe(rows)


def _chosun() -> list[tuple[str, str]]:
    url = "https://www.chosun.com/economy/tech_it/"
    x = _get(url)
    # 맨 위 기사는 관련 기사 묶음(링크 없음)과 함께 오므로, 링크 대신 제목 등장 순서만 쓴다
    titles = re.findall(r'"headlines":\{"basic":"((?:[^"\\]|\\.)*)"', x)
    return _dedupe([(_clean(t), f"{url}#{i}") for i, t in enumerate(titles)])


SITES = [
    # (이름, 읽는 함수, AI 필터 적용 여부)
    ("NBC 뉴스 AI 섹션", _nbc, True),  # 아래쪽에 일반 뉴스 목록이 섞여 있어 필터 적용
    ("ABC 뉴스 기술 섹션", _abc, True),
    ("Techmeme 첫 화면", _techmeme, True),
    ("조선일보 테크·IT 섹션", _chosun, True),
]


def collect_rankings() -> list[dict]:
    """[{"site": 이름, "items": [{"rank": 1, "title": ..., "url": ...}, ...]}, ...]"""
    result = []
    for name, fn, ai_filter in SITES:
        try:
            rows = fn()
        except Exception as exc:  # noqa: BLE001 - 사이트 하나 실패해도 계속
            print(f"[rankings] {name} 읽기 실패: {exc}", file=sys.stderr)
            continue
        if len(rows) < MIN_ITEMS:
            print(f"[rankings] {name}: {len(rows)}개만 읽힘 — 페이지 구조 변경 의심, 건너뜀", file=sys.stderr)
            continue
        if ai_filter:
            rows = [r for r in rows if _is_ai(r[0])]
        items = [{"rank": i, "title": t, "url": u} for i, (t, u) in enumerate(rows[:TOP_N], start=1)]
        print(f"[rankings] {name}: AI 관련 상위 {len(items)}개")
        result.append({"site": name, "items": items})
    return result


if __name__ == "__main__":
    for site in collect_rankings():
        print(f"\n== {site['site']}")
        for it in site["items"]:
            print(f"  {it['rank']:2}. {it['title'][:90]}")
