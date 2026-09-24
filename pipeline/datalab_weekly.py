# -*- coding: utf-8 -*-
"""네이버 데이터랩 쇼핑인사이트 인기검색어(헤어케어·헤어기기)를 주 1회 카카오톡으로 보낸다.
GitHub Actions datalab-weekly.yml에서 호출한다.
"""
from __future__ import annotations

import datetime as dt
import sys

import requests

from send_kakao import send_text_with_button

DATALAB = "https://datalab.naver.com/shoppingInsight"
PAGE_URL = f"{DATALAB}/sCategory.naver"
H = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    "Referer": PAGE_URL,
    "Origin": "https://datalab.naver.com",
    "X-Requested-With": "XMLHttpRequest",
}

# (이름, cid) — cid는 데이터랩 카테고리 트리에서 확인한 값
CATEGORIES = [
    ("헤어케어", 50000198),   # 화장품/미용 > 헤어케어
    ("헤어기기", 50015561),   # 디지털/가전 > 이미용가전 > 헤어기기
]
AGE = "30,40,50"
GENDER = "f"
TOP_N = 10
KAKAO_TEXT_LIMIT = 200  # 카카오 텍스트 템플릿 최대 길이


def fetch_ranks(s: requests.Session, cid: int, start: dt.date, end: dt.date) -> list[dict]:
    r = s.post(f"{DATALAB}/getCategoryKeywordRank.naver", headers=H, timeout=20,
               data={"cid": cid, "timeUnit": "date", "startDate": start.isoformat(),
                     "endDate": end.isoformat(), "age": AGE, "gender": GENDER,
                     "device": "", "page": 1, "count": 20})
    r.raise_for_status()
    ranks = r.json().get("ranks") or []
    if not ranks:
        raise RuntimeError(f"cid {cid} 순위가 비어 있음: {r.text[:200]}")
    return ranks


def build_text(name: str, ranks: list[dict], start: dt.date, end: dt.date) -> str:
    header = f"📊 {name} 인기검색어 TOP{TOP_N}\n여성 30~50대 · {start:%m/%d}~{end:%m/%d}\n\n"
    lines = [f"{k['rank']}. {k['keyword']}" for k in ranks[:TOP_N]]
    text = header + "\n".join(lines)
    while len(text) > KAKAO_TEXT_LIMIT and lines:
        lines.pop()
        text = header + "\n".join(lines)
    return text


def main() -> None:
    # 어제까지 최근 7일
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=6)

    s = requests.Session()
    s.get(PAGE_URL, headers=H, timeout=20).raise_for_status()

    messages = []
    for name, cid in CATEGORIES:
        ranks = fetch_ranks(s, cid, start, end)
        text = build_text(name, ranks, start, end)
        print(text, end="\n\n")
        messages.append(text)

    for text in messages:
        send_text_with_button(text, "데이터랩에서 보기", PAGE_URL)
    print(f"[datalab_weekly] 카카오톡 {len(messages)}건 전송 완료")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"[datalab_weekly] 실패: {exc}", file=sys.stderr)
        raise
