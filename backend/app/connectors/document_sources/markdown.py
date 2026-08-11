"""MD parser: # / ## / ### → Section level; non-heading lines → text; GFM | tables → table."""

from __future__ import annotations

import re

from app.knowledge.document_models import Block, Document, Section, Table, TablePageSegment

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_SEP = re.compile(r"^:?-{2,}:?$")


def parse_md(content: bytes) -> Document:
    text = content.decode("utf-8", errors="replace")
    root = Section(level=0, title=None, synthetic=True)
    stack: list[Section] = [root]
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = _HEADING.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            new_sec = Section(level=level, title=title)
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
            stack[-1].children.append(new_sec)
            stack.append(new_sec)
            i += 1
        elif line.startswith("|"):
            tbl_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl_lines.append(lines[i].strip())
                i += 1
            table = _parse_md_table(tbl_lines)
            if table is not None:
                stack[-1].blocks.append(Block(type="table", table=table))
            else:
                for ln in tbl_lines:
                    stack[-1].blocks.append(Block(type="text", content=ln))
        elif line:
            stack[-1].blocks.append(Block(type="text", content=line))
            i += 1
        else:
            i += 1
    return Document(root=root)


def _parse_md_table(lines: list[str]) -> Table | None:
    rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines]
    sep_idx = None
    for idx, r in enumerate(rows):
        if r and all(_TABLE_SEP.match(c or "-") for c in r):
            sep_idx = idx
            break
    if sep_idx is None or sep_idx == 0:
        return None
    header = rows[0]
    data = rows[sep_idx + 1:]
    if not data:
        return None
    return Table(
        table_id=f"md_table_{id(lines)}",
        canonical_header=[header],
        column_count=len(header),
        page_segments=[TablePageSegment(page=None, rows=data)],
    )
