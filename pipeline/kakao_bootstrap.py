"""1회성 스크립트: 카카오 인가 코드(code)를 access_token/refresh_token으로 교환한다.
브라우저에서 인가 코드를 받은 뒤 이 스크립트를 로컬에서 딱 한 번 실행하면 된다.
결과로 나온 refresh_token을 GitHub Secret(KAKAO_REFRESH_TOKEN)에 등록하면 끝.

사용법:
  KAKAO_REST_API_KEY=... python pipeline/kakao_bootstrap.py <REDIRECT_URI> <CODE>
"""
from __future__ import annotations

import os
import sys

import requests

TOKEN_URL = "https://kauth.kakao.com/oauth/token"


def main() -> None:
    if len(sys.argv) < 3:
        print("사용법: python pipeline/kakao_bootstrap.py <REDIRECT_URI> <CODE>")
        raise SystemExit(1)

    redirect_uri, code = sys.argv[1], sys.argv[2]
    rest_api_key = os.environ["KAKAO_REST_API_KEY"]
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET")

    data = {
        "grant_type": "authorization_code",
        "client_id": rest_api_key,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if client_secret:
        data["client_secret"] = client_secret

    resp = requests.post(TOKEN_URL, data=data, timeout=15)
    if resp.status_code != 200:
        print(f"토큰 발급 실패 ({resp.status_code}): {resp.text}")
        raise SystemExit(1)

    payload = resp.json()
    print("\n토큰 발급 성공! 아래 refresh_token을 GitHub Secret 'KAKAO_REFRESH_TOKEN'에 등록하세요.\n")
    print(f"access_token  (참고용, 곧 만료됨): {payload['access_token']}")
    print(f"refresh_token (이걸 등록하세요!):   {payload['refresh_token']}")


if __name__ == "__main__":
    main()
