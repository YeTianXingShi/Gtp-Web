from __future__ import annotations

import argparse

from itsdangerous import URLSafeTimedSerializer

from gtpweb.config import load_config
from gtpweb.user_store import get_user_record


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a signed magic login link.")
    parser.add_argument("username", help="Target username")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Public base URL, for example https://gtp26.zhensnow.uk",
    )
    parser.add_argument(
        "--next",
        dest="next_url",
        default="",
        help="Optional redirect path after login, for example /chat",
    )
    args = parser.parse_args()

    config = load_config()
    record = get_user_record(config.users_file, args.username)
    if record is None:
        raise SystemExit(f"Unknown user: {args.username}")

    serializer = URLSafeTimedSerializer(config.magic_login_secret, salt="magic-login")
    payload = {"username": record["username"]}
    if args.next_url:
        payload["next"] = args.next_url
    token = serializer.dumps(payload)

    base_url = args.base_url.rstrip("/")
    print(f"{base_url}/login/magic?token={token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
