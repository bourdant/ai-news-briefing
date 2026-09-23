"""Kakao refresh_token으로 access_token을 새로 발급받는다.
응답에 새 refresh_token이 포함되면(카카오가 회전시킨 경우) GitHub Actions Secret
KAKAO_REFRESH_TOKEN을 자동으로 갱신한다 (GH_PAT, GITHUB_REPOSITORY 환경변수 필요).
"""
from __future__ import annotations

import base64
import os
import sys

import requests

TOKEN_URL = "https://kauth.kakao.com/oauth/token"


def refresh_access_token() -> str:
    rest_api_key = os.environ["KAKAO_REST_API_KEY"]
    refresh_token = os.environ["KAKAO_REFRESH_TOKEN"]
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET")  # 앱에서 활성화한 경우만

    data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    if client_secret:
        data["client_secret"] = client_secret

    resp = requests.post(TOKEN_URL, data=data, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Kakao 토큰 갱신 실패 ({resp.status_code}): {resp.text}")

    payload = resp.json()
    access_token = payload["access_token"]

    new_refresh_token = payload.get("refresh_token")
    if new_refresh_token and new_refresh_token != refresh_token:
        print("[kakao_token] refresh_token이 회전되어 GitHub Secret을 갱신합니다.", file=sys.stderr)
        _update_github_secret("KAKAO_REFRESH_TOKEN", new_refresh_token)

    return access_token


def _update_github_secret(name: str, value: str) -> None:
    try:
        from nacl import encoding, public
    except ImportError as exc:
        raise RuntimeError(
            "PyNaCl이 설치되어 있지 않아 GitHub Secret을 자동 갱신할 수 없습니다. "
            "requirements.txt를 확인하세요."
        ) from exc

    gh_pat = os.environ.get("GH_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY")  # "owner/repo", Actions가 자동 제공
    if not gh_pat or not repo:
        print(
            "[kakao_token] GH_PAT 또는 GITHUB_REPOSITORY가 없어 Secret 자동 갱신을 건너뜁니다. "
            "refresh_token이 곧 만료될 수 있으니 수동으로 KAKAO_REFRESH_TOKEN을 갱신하세요.",
            file=sys.stderr,
        )
        return

    headers = {
        "Authorization": f"Bearer {gh_pat}",
        "Accept": "application/vnd.github+json",
    }
    key_resp = requests.get(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        headers=headers,
        timeout=15,
    )
    key_resp.raise_for_status()
    key_data = key_resp.json()

    public_key = public.PublicKey(key_data["key"].encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(value.encode("utf-8"))
    encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")

    put_resp = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/{name}",
        headers=headers,
        json={"encrypted_value": encrypted_b64, "key_id": key_data["key_id"]},
        timeout=15,
    )
    put_resp.raise_for_status()
    print(f"[kakao_token] GitHub Secret {name} 갱신 완료.", file=sys.stderr)


if __name__ == "__main__":
    token = refresh_access_token()
    print(f"access_token 발급 완료 (길이 {len(token)})")
