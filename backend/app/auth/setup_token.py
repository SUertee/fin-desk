"""Generate a one-time owner setup code and its non-reversible digest."""

from __future__ import annotations

import secrets

from app.auth.service import token_digest


def main() -> None:
    token = secrets.token_urlsafe(32)
    print(f"Setup code (shown once): {token}")
    print(f"AUTH_SETUP_TOKEN_HASH={token_digest(token)}")


if __name__ == "__main__":
    main()
