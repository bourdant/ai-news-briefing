"""GitHub Actions Secret을 코드에서 저장/갱신한다 (GH_PAT, GITHUB_REPOSITORY 환경변수 필요)."""
from __future__ import annotations

import base64
import os
import sys

import requests


def update_github_secret(name: str, value: str) -> None:
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
            f"[github_secret] GH_PAT 또는 GITHUB_REPOSITORY가 없어 Secret {name} 저장을 건너뜁니다. "
            "필요하면 저장소 Settings → Secrets에서 직접 등록하세요.",
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
    print(f"[github_secret] GitHub Secret {name} 갱신 완료.", file=sys.stderr)

