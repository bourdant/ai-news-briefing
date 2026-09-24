# -*- coding: utf-8 -*-
"""네이버 데이터랩 쇼핑인사이트 인기검색어(헤어케어·헤어기기)를 주 1회 텔레그램으로 보낸다.
전주 대비 새로 진입했거나 3계단 이상 오른 검색어는 Claude가 웹 검색으로 이유를 분석해 따로 보낸다.
GitHub Actions datalab-weekly.yml에서 호출한다.
"""
from __future__ import annotations

import datetime as dt
import sys

import requests

from claude_cli import run_claude
from send_telegram import send_text, send_text_with_button

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
TOP_N = 15
RISE_THRESHOLD = 3  # 전주 대비 이 계단 이상 오르면 분석 대상

ANALYSIS_SYSTEM = (
    "당신은 한국 뷰티·헤어 시장 트렌드 분석가입니다. 네이버 쇼핑 인기검색어 순위에서 "
    "급상승하거나 새로 진입한 검색어마다 웹 검색으로 최근 1~2주 소식(신제품 출시, 할인·방송·공동구매, "
    "SNS 입소문, 계절·명절 요인, 논란 등)을 찾아 순위가 오른 이유를 분석합니다.\n"
    "규칙:\n"
    "- 친근한 존댓말 한국어, 마크다운 문법(#, **, 표) 없이 순수 텍스트로 씁니다.\n"
    "- 검색어마다 '▸ 검색어 (변동)' 한 줄 뒤에 2~3문장: 무엇인지 → 왜 올랐는지. "
    "신제품이 나왔는지는 꼭 밝힙니다.\n"
    "- 근거를 찾은 내용과 추정을 구분하고, 추정은 문장 끝에 '(추정)'을 붙입니다.\n"
    "- 브랜드가 아닌 일반 검색어(예: 염색샴푸)는 그 수요가 늘어난 이유를 분석합니다.\n"
    "- 맨 끝에 '한 줄 요약:' 한 문장, 그 다음 줄에 '출처:'와 근거로 쓴 URL을 최대 5개 나열합니다.\n"
    "- 전체 2500자 이내. 인사말이나 서론 없이 바로 시작합니다."
)


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


def change_label(rank: int, prev: int | None) -> str:
    """전주 순위 대비 변동. 분석 대상이 아니면 빈 문자열."""
    if prev is None or prev > TOP_N:
        return "신규 진입" + ("" if prev is None else f", 전주 {prev}위")
    if prev - rank >= RISE_THRESHOLD:
        return f"{prev}위→{rank}위, ▲{prev - rank}"
    return ""


def build_section(name: str, ranks: list[dict], prev: dict[str, int]) -> tuple[str, list[str]]:
    lines, movers = [], []
    for k in ranks[:TOP_N]:
        label = change_label(k["rank"], prev.get(k["keyword"]))
        mark = ""
        if label:
            mark = " 🆕" if label.startswith("신규") else f" ▲{prev[k['keyword']] - k['rank']}"
            movers.append(f"[{name}] {k['keyword']} ({label})")
        lines.append(f"{k['rank']}. {k['keyword']}{mark}")
    return f"■ {name} TOP{TOP_N}\n" + "\n".join(lines), movers


def analyze(movers: list[str], start: dt.date, end: dt.date) -> str:
    prompt = (
        f"기간: {start}~{end} (여성 30~50대, 네이버 쇼핑인사이트)\n"
        f"전주 대비 새로 진입했거나 {RISE_THRESHOLD}계단 이상 오른 검색어:\n"
        + "\n".join(f"- {m}" for m in movers)
        + "\n\n각 검색어가 순위에 오른 이유를 분석해 주세요."
    )
    envelope = run_claude(prompt=prompt, system_prompt=ANALYSIS_SYSTEM,
                          allowed_tools="WebSearch", timeout=900)
    return (envelope.get("result") or "").strip()


def main() -> None:
    # 어제까지 최근 7일, 그리고 그 전 7일
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=6)
    prev_end = start - dt.timedelta(days=1)
    prev_start = prev_end - dt.timedelta(days=6)

    s = requests.Session()
    s.get(PAGE_URL, headers=H, timeout=20).raise_for_status()

    sections, movers = [], []
    for name, cid in CATEGORIES:
        prev = {k["keyword"]: k["rank"] for k in fetch_ranks(s, cid, prev_start, prev_end)}
        section, m = build_section(name, fetch_ranks(s, cid, start, end), prev)
        sections.append(section)
        movers += m

    header = f"📊 헤어 인기검색어 주간 순위\n여성 30~50대 · {start:%m/%d}~{end:%m/%d}\n🆕 신규 진입 · ▲ 전주 대비 상승"
    text = "\n\n".join([header, *sections])
    print(text)
    send_text_with_button(text, "데이터랩에서 보기", PAGE_URL)
    print("[datalab_weekly] 순위 전송 완료")

    if not movers:
        print("[datalab_weekly] 급상승·신규 진입 검색어 없음 — 분석 생략")
        return

    print("[datalab_weekly] 분석 대상:", *movers, sep="\n  ")
    analysis = analyze(movers, start, end)
    print(analysis)
    send_text(f"🔎 급상승·신규 진입 검색어 분석 ({start:%m/%d}~{end:%m/%d})\n\n{analysis}")
    print("[datalab_weekly] 분석 전송 완료")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"[datalab_weekly] 실패: {exc}", file=sys.stderr)
        raise
