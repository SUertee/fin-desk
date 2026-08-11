"""Shared table helpers (header detection + Table construction)."""

from __future__ import annotations

from app.knowledge.document_models import Table, TablePageSegment

HEADER_CELL_MAX_LEN = 30  # 表头 cell 超此字数视为不像表头(说明/须知/数据行)


def row_looks_header(row: list[str]) -> bool:
    """像表头: >=2 列非空 且 cells 都短(<= HEADER_CELL_MAX_LEN)。"""
    nonempty = [c for c in row if (c or "").strip()]
    if len(nonempty) < 2:
        return False
    return all(len(str(c).strip()) <= HEADER_CELL_MAX_LEN for c in nonempty)


def normalize_table_header(rows: list[list[str]]) -> list[list[str]]:
    """首行不像表头 → 向后找真表头; 找不到原样返回。"""
    if not rows or row_looks_header(rows[0]):
        return rows
    for k in range(1, len(rows)):
        if row_looks_header(rows[k]):
            return [rows[k]] + rows[k + 1:]
    return rows


def make_table(
    rows: list[list[str]],
    table_id: str,
    page: int | None,
    col_count: int | None = None,
) -> Table:
    """从 rows 构造 Table(首行表头 + 其余数据行, 单 page_segment)。"""
    return Table(
        table_id=table_id,
        canonical_header=[rows[0]],
        column_count=col_count or max(len(r) for r in rows),
        page_segments=[TablePageSegment(page=page, rows=rows[1:])],
    )
