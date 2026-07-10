"""Encoding detection for uploaded statement files."""

from __future__ import annotations


def decode_statement_bytes(raw: bytes) -> tuple[str, str]:
    """Decode statement bytes, returning (text, encoding_name).

    UTF-8 (with or without BOM) is tried strictly first; Alipay exports are
    GB18030 (a superset of GBK), which is the fallback. GB18030 accepts almost
    any byte sequence, so it must come last.
    """

    try:
        return raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        pass
    return raw.decode("gb18030"), "gb18030"
