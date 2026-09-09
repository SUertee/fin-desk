"""Argon2 password hashing helpers and an interactive provisioning command."""

from __future__ import annotations

import getpass
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _password_hasher() -> tuple[Any, tuple[type[Exception], ...]]:
    """Load the optional auth dependency only when password auth is used.

    Local single-user deployments can run with authentication disabled. Keeping
    this import lazy lets those deployments start from an older cached image,
    while enabled authentication still fails closed when Argon2 is unavailable.
    """
    try:
        from argon2 import PasswordHasher
        from argon2.exceptions import (
            InvalidHashError,
            VerificationError,
            VerifyMismatchError,
        )
    except ImportError as exc:
        raise RuntimeError(
            "argon2-cffi is required when FinDesk password authentication is enabled"
        ) from exc
    return PasswordHasher(), (InvalidHashError, VerificationError, VerifyMismatchError)


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    hasher, _errors = _password_hasher()
    return hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    hasher, errors = _password_hasher()
    try:
        return hasher.verify(password_hash, password)
    except errors:
        return False


def main() -> None:
    password = getpass.getpass("New FinDesk password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    print(hash_password(password))


if __name__ == "__main__":
    main()
