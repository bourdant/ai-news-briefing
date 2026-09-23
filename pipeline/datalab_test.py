# -*- coding: utf-8 -*-
"""GitHub Actions 서버에서 네이버 데이터랩 접속이 되는지 시험 (카톡 전송 없음)"""
import datetime as dt
import sys

import requests

H = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    "Referer": "https://datalab.naver.com/shoppingInsight/sCategory.naver",
    "Origin": "https://datalab.naver.com",
    "X-Requested-With": "XMLHttpRequest",
}
s = requests.Session()


def step(name, fn):
    try:
        out = fn()
        print(f"✅ {name}")
        return out
    except Exception as e:
        print(f"❌ {name} 실패: {e}")
        print("\n결론: 이 서버에서는 네이버 데이터랩 접속이 막혀 있어요 → 1번(따로 두기) 방법으로 가야 해요.")
        sys.exit(1)


def find(cid, name):
    r = s.get("https://datalab.naver.com/shoppingInsight/getCategory.naver",
              params={"cid": cid}, headers=H, timeout=20)
    r.raise_for_status()
    for k in r.json()["childList"]:
        if k["name"].replace(" ", "") == name:
            return k["cid"]
    raise RuntimeError(f"'{name}' 없음")


step("1. 데이터랩 페이지 접속", lambda: s.get(
    "https://datalab.naver.com/shoppingInsight/sCategory.naver", headers=H, timeout=20).raise_for_status())
beauty = step("2. 카테고리 목록 조회", lambda: find(0, "화장품/미용"))
hair = step("3. 헤어케어 찾기", lambda: find(beauty, "헤어케어"))

end = dt.date.today() - dt.timedelta(days=1)
start = end - dt.timedelta(days=6)


def rank():
    r = s.post("https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver", headers=H, timeout=20,
               data={"cid": hair, "timeUnit": "date", "startDate": start.isoformat(),
                     "endDate": end.isoformat(), "age": "30,40,50", "gender": "f",
                     "device": "", "page": 1, "count": 20})
    r.raise_for_status()
    ranks = r.json().get("ranks") or []
    if not ranks:
        raise RuntimeError(f"순위가 비어 있음: {r.text[:200]}")
    return ranks


ranks = step("4. 인기검색어 조회", rank)
print(f"\n[헤어케어 · 여성 30~50대 · {start}~{end}]")
for r in ranks[:15]:
    print(f"{r['rank']}. {r['keyword']}")
print("\n결론: 이 서버에서 네이버 데이터랩 접속 가능 → 2번(합치기) 방법으로 가도 돼요.")
