"""用户文档切片算法。

输入 Document(标题树), 输出 [Chunk(chunk_text + meta)]。
规则(v3.1 + B): 层级递归 + 整塞优先 + B 降级(延迟渲染 TextFragment + 跨 path 组合)
+ breadcrumb 进 chunk_text + MAX 硬 1500 / TARGET_MIN 软 100 + 句末边界零 overlap
+ table 结构化每 chunk 表头 + PDF/PPT 不跨物理页 + 路径数上限(防稀释)。
纯算法, 不 embed/存库/解析文件。
"""

from __future__ import annotations

from app.knowledge.document_models import Block, Chunk, Document, Section, Table, TextFragment

MAX_SIZE = 1500
TARGET_MIN = 100
MAX_PATHS_PER_CHUNK = 6   # B: 单 chunk 最多 6 个不同 path(防过度合并稀释检索)
# Why 0.5：优先区命中率与切点别太靠前的平衡；一期默认，后续按真实文档填充率观察调整
BOUNDARY_WINDOW_RATIO = 0.5
# Why 分号升第一级：分号是句间停顿（并列分句），语义权重接近句末，优先作为切点
_SENTENCE_END = "。！？.!?;；"   # 第一级（句末 + 分号），中英文兼容
_SUB_SENTENCE = "，,"            # 第二级（逗号）


class TableHeaderTooLarge(Exception):
    """表头本身 ≥ MAX_SIZE, 无法产出完整子表。"""


class BreadcrumbTooLarge(Exception):
    """breadcrumb + 换行 ≥ MAX_SIZE → available ≤ 0, while 会死循环; 显式报错不挂死 worker。"""


class SingleRowTooLarge(Exception):
    """单条数据行 > available(即使 cur_rows 空); 纵向/cell 切后补, 首期 raise。"""


# ── 主入口 ──────────────────────────────────────────────

def chunk_document(doc: Document) -> list[Chunk]:
    chunks: list[Chunk] = []
    # 序言(root.blocks, 无标题): 走 _split_blocks(path=[], 简单)
    if doc.root.blocks:
        chunks += _split_blocks(doc.root.blocks, section_path=[], default_page=doc.root.page)
    # 每个 H1 独立(不跨 H1 合并)
    for h1 in doc.root.children:
        chunks += _split_section(h1, section_path=[h1.title])
    return chunks


# ── Section 递归(整塞优先 + B 降级)──────────────────────

def _split_section(section: Section, section_path: list[str]) -> list[Chunk]:
    all_blocks = _collect_blocks(section)
    # 整塞: 全 text + 同 page + 渲染 ≤ MAX
    if (
        all_blocks
        and all(b.type == "text" for b in all_blocks)
        and _same_page(all_blocks)
    ):
        rendered = _render_whole_section(section, section_path)
        if len(rendered) <= MAX_SIZE:
            return [Chunk(chunk_text=rendered, meta={
                "type": "text",
                "section_path": _breadcrumb(section_path),
                "page": _first_page(all_blocks),
            })]
    # B 降级: 收集 fragments + pack 组合 + 延迟渲染
    return _split_section_b(section, section_path)


# ── B 降级: fragment 收集 + pack + render ──────────────

def _split_section_b(section: Section, section_path: list[str]) -> list[Chunk]:
    """B 降级: DFT 收集 text fragments + table/image 硬边界 + pack 组合 + 延迟渲染。"""
    chunks: list[Chunk] = []
    frag_buf: list[TextFragment] = []

    def flush_frags():
        if frag_buf:
            for group in _pack_fragments(frag_buf):
                chunks.append(_render_group(group, frag_buf[0].page))
            frag_buf.clear()   # 不用 frag_buf=[](_walk_collect 持同一引用, 赋值会失效)

    _walk_collect(section, section_path, frag_buf, flush_frags, chunks, section.page)
    flush_frags()
    return chunks


def _walk_collect(
    section: Section, section_path: list[str],
    frag_buf: list[TextFragment], flush_frags, chunks: list[Chunk],
    default_page: int | None,
) -> None:
    """DFT 遍历 section(blocks + children), 产 fragments + table/image 硬边界。"""
    for b in section.blocks:
        if b.type == "text" and b.content:
            bpage = b.page or default_page
            if frag_buf and frag_buf[-1].page != bpage:
                flush_frags()   # 跨页 flush
            # 预切判断: 渲染后(breadcrumb+换行+payload)>MAX → _split_text 切(不 raise)
            prefix_len = len(_breadcrumb(section_path)) + (2 if section_path else 0)
            if prefix_len + len(b.content) > MAX_SIZE:
                flush_frags()
                chunks.extend(_split_text(b.content, section_path, bpage, "text"))
            else:
                frag_buf.append(TextFragment(
                    payload=b.content, path=list(section_path),
                    level=section.level, page=bpage,
                ))
        elif b.type == "table" and b.table:
            flush_frags()
            chunks.extend(_chunk_table(b.table, section_path, b.page or default_page))
        elif b.type == "image" and b.caption:
            flush_frags()
            chunks.extend(_split_text(
                b.caption, section_path, b.page or default_page, "image",
                {"oss_key": b.image_oss_key},
            ))
    for child in section.children:
        _walk_collect(
            child, section_path + [child.title],
            frag_buf, flush_frags, chunks, child.page or default_page,
        )


def _pack_fragments(frags: list[TextFragment]) -> list[list[TextFragment]]:
    """贪婪组合相邻 fragment(同 page + 路径数 ≤ 上限 + 渲染 ≤ MAX)。"""
    groups: list[list[TextFragment]] = []
    cur: list[TextFragment] = [frags[0]]
    for f in frags[1:]:
        trial = cur + [f]
        paths_count = len({tuple(g.path) for g in trial})
        if (
            f.page == cur[-1].page
            and paths_count <= MAX_PATHS_PER_CHUNK
            and len(_render_group_text(trial)) <= MAX_SIZE
        ):
            cur = trial
        else:
            groups.append(cur)
            cur = [f]
    if cur:
        groups.append(cur)
    return groups


def _render_group_text(group: list[TextFragment]) -> str:
    """渲染 group → chunk_text(共同祖先 breadcrumb + 每 fragment 局部 ## + payload)。"""
    paths = [f.path for f in group]
    ancestor = _common_ancestor(paths)
    parts: list[str] = []
    if ancestor:
        parts.append(_breadcrumb(ancestor))
    prev_path: list[str] | None = None
    for f in group:
        if f.path != prev_path:
            # 同 path 只首个带局部标题(后续同 path 是续文, 不重复 ##)
            local = _local_title(f, ancestor)
            if local:
                parts.append(local)
        parts.append(f.payload)
        prev_path = f.path
    return "\n\n".join(parts)


def _render_group(group: list[TextFragment], page: int | None) -> Chunk:
    """group → Chunk(chunk_text + meta 双字段 section_path/section_paths)。"""
    chunk_text = _render_group_text(group)
    if len(chunk_text) > MAX_SIZE:
        raise BreadcrumbTooLarge(f"渲染后 {len(chunk_text)} > MAX, breadcrumb 可能过长")
    paths = [f.path for f in group]
    ancestor = _common_ancestor(paths)
    return Chunk(chunk_text=chunk_text, meta={
        "type": "text",
        "section_path": _breadcrumb(ancestor),
        "section_paths": list(dict.fromkeys(_breadcrumb(p) for p in paths)),   # 保序去重
        "page": page,
    })


def _common_ancestor(paths: list[list[str]]) -> list[str]:
    """最长公共前缀(共同祖先)。"""
    if not paths:
        return []
    ancestor = list(paths[0])
    for p in paths[1:]:
        new_len = 0
        for i in range(min(len(ancestor), len(p))):
            if ancestor[i] == p[i]:
                new_len = i + 1
            else:
                break
        ancestor = ancestor[:new_len]
    return ancestor


def _local_title(frag: TextFragment, ancestor: list[str]) -> str:
    """path 去共同祖先后剩余 → 局部标题(用 frag.level 真实层级, 不用 path 推)。"""
    remaining = frag.path[len(ancestor):]
    if not remaining:
        return ""
    return "#" * min(frag.level, 6) + " " + " > ".join(remaining)


# ── 整塞辅助 ───────────────────────────────────────────

def _same_page(blocks: list[Block]) -> bool:
    pages = {b.page for b in blocks}
    return len(pages) <= 1


def _first_page(blocks: list[Block]) -> int | None:
    for b in blocks:
        if b.page is not None:
            return b.page
    return None


def _collect_blocks(section: Section) -> list[Block]:
    out = list(section.blocks)
    for child in section.children:
        out.extend(_collect_blocks(child))
    return out


def _render_whole_section(section: Section, section_path: list[str]) -> str:
    parts: list[str] = []
    breadcrumb = _breadcrumb(section_path)
    if breadcrumb:
        parts.append(breadcrumb)
    _render_section_body(section, parts)
    return "\n\n".join(parts)


def _render_section_body(section: Section, parts: list[str]) -> None:
    for b in section.blocks:
        t = _block_text(b)
        if t:
            parts.append(t)
    for child in section.children:
        if child.title:
            parts.append("#" * min(child.level, 6) + " " + child.title)
        _render_section_body(child, parts)


# ── 序言切分(_split_blocks, 只服务 root.blocks 无标题)──

def _split_blocks(
    blocks: list[Block], section_path: list[str], default_page: int | None
) -> list[Chunk]:
    """序言/无标题 blocks 切分(path=[], 简单 text_buf + table/image 硬边界)。"""
    chunks: list[Chunk] = []
    text_buf: list[str] = []
    cur_page: int | None = None

    def flush_text():
        nonlocal text_buf
        if text_buf:
            text = "\n\n".join(text_buf)
            chunks.extend(_split_text(text, section_path, cur_page, "text"))
            text_buf = []

    for b in blocks:
        if b.type == "text" and b.content:
            bpage = b.page or default_page
            if text_buf and bpage != cur_page:
                flush_text()
            if not text_buf:
                cur_page = bpage
            text_buf.append(b.content)
        elif b.type == "table" and b.table:
            flush_text()
            chunks.extend(_chunk_table(b.table, section_path, b.page or default_page))
        elif b.type == "image" and b.caption:
            flush_text()
            chunks.extend(_split_text(
                b.caption, section_path, b.page or default_page, "image",
                {"oss_key": b.image_oss_key},
            ))
    flush_text()
    _merge_short_tails(chunks)
    return chunks


# ── 文本切分(序言/image caption/超长 payload 用)────────

def _split_text(
    text: str, section_path: list[str], page: int | None,
    chunk_type: str, extra_meta: dict | None = None,
) -> list[Chunk]:
    breadcrumb = _breadcrumb(section_path)
    prefix = (breadcrumb + "\n\n") if breadcrumb else ""
    available = MAX_SIZE - len(prefix)
    if available <= 0:
        raise BreadcrumbTooLarge(
            f"breadcrumb({len(breadcrumb)}) ≥ MAX_SIZE, 路径={breadcrumb}"
        )
    base_meta = {"type": chunk_type, "section_path": _breadcrumb(section_path), "page": page}
    if extra_meta:
        base_meta.update(extra_meta)

    chunks: list[Chunk] = []
    remaining = text
    while True:
        if not remaining.strip():
            break
        if len(prefix) + len(remaining) <= MAX_SIZE:
            chunks.append(Chunk(chunk_text=prefix + remaining, meta=dict(base_meta)))
            break
        cut = _find_sentence_boundary(remaining, available)
        if cut == 0:
            cut = available
        piece = remaining[:cut]
        remaining = remaining[cut:].lstrip("\n")
        if piece.strip():
            chunks.append(Chunk(chunk_text=prefix + piece, meta=dict(base_meta)))
    return chunks


def _rfind_boundary(text: str, chars: str, lo: int, hi: int) -> int:
    """在 [lo, hi) 从后往前找 chars 里的字符；命中返回 i+1（切在标点后），不命中返回 0。

    Why 左闭右开 [lo, hi)：和 Python slice 语义一致（text[lo:hi]）。
    """
    for i in range(min(hi, len(text)) - 1, lo - 1, -1):
        if text[i] in chars:
            return i + 1
    return 0


def _find_sentence_boundary(text: str, max_pos: int) -> int:
    """窗口化找切点，防几字孤儿：min_cut=TARGET_MIN 卡绝对下限。

    4 级降级：优先区[near_start,end) 句末 → 优先区逗号 → 兜底区[min_cut,near_start) 句末 → 兜底区逗号 → 0。
    Why 窗口化：旧实现全范围扫，远句号（如位置 3）会被选中，切出几字孤儿。
    """
    end = min(max_pos, len(text))
    min_cut = min(end, TARGET_MIN)
    near_start = max(min_cut, int(end * BOUNDARY_WINDOW_RATIO))

    # 优先区
    cut = _rfind_boundary(text, _SENTENCE_END, near_start, end)
    if cut:
        return cut
    cut = _rfind_boundary(text, _SUB_SENTENCE, near_start, end)
    if cut:
        return cut
    # 兜底区（不低于 TARGET_MIN）
    cut = _rfind_boundary(text, _SENTENCE_END, min_cut, near_start)
    if cut:
        return cut
    cut = _rfind_boundary(text, _SUB_SENTENCE, min_cut, near_start)
    if cut:
        return cut
    return 0


# ── 表格切分(按 page_segment + 每 chunk 表头)────────────

def _chunk_table(table: Table, section_path: list[str], default_page: int | None) -> list[Chunk]:
    header_md = _render_header(table.canonical_header, table.column_count)
    breadcrumb = _breadcrumb(section_path)
    prefix = (breadcrumb + "\n\n") if breadcrumb else ""
    available = MAX_SIZE - len(prefix) - len(header_md)
    if available <= 0:
        raise TableHeaderTooLarge(f"table {table.table_id}: 表头+prefix ≥ MAX_SIZE")

    chunks: list[Chunk] = []
    for seg in table.page_segments:
        cur_rows: list[list[str]] = []
        cur_len = 0
        seg_page = seg.page or default_page
        for row in seg.rows:
            row_md = "| " + " | ".join(_escape_cell(c) for c in row) + " |"
            row_len = len(row_md) + 1
            if row_len > available:
                raise SingleRowTooLarge(f"table {table.table_id}: 单行({row_len}) > available({available})")
            if cur_rows and cur_len + row_len > available:
                chunks.append(_make_table_chunk(prefix, header_md, cur_rows, table, section_path, seg_page))
                cur_rows = []
                cur_len = 0
            cur_rows.append(row)
            cur_len += row_len
        if cur_rows:
            chunks.append(_make_table_chunk(prefix, header_md, cur_rows, table, section_path, seg_page))
    return chunks


def _make_table_chunk(
    prefix: str, header_md: str, rows: list[list[str]],
    table: Table, section_path: list[str], page: int | None,
) -> Chunk:
    body = "\n".join("| " + " | ".join(_escape_cell(c) for c in row) + " |" for row in rows)
    return Chunk(chunk_text=prefix + header_md + "\n" + body, meta={
        "type": "table", "section_path": _breadcrumb(section_path),
        "page": page, "table_id": table.table_id,
    })


def _render_header(header_rows: list[list[str]], column_count: int) -> str:
    lines: list[str] = []
    for row in header_rows:
        cells = [_escape_cell(c) for c in row]
        while len(cells) < column_count:
            cells.append("")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("| " + " | ".join(["---"] * column_count) + " |")
    return "\n".join(lines)


# ── 短尾合并(只 text, 序言用)───────────────────────────

def _merge_short_tails(chunks: list[Chunk]) -> None:
    if len(chunks) < 2:
        return
    merged: list[Chunk] = [chunks[0]]
    for c in chunks[1:]:
        prev = merged[-1]
        if (
            c.meta.get("type") == "text"
            and prev.meta.get("type") == "text"
            and len(c.chunk_text) < TARGET_MIN
            and c.meta.get("section_path") == prev.meta.get("section_path")
            and c.meta.get("page") == prev.meta.get("page")
            and len(prev.chunk_text) + 2 + len(c.chunk_text) <= MAX_SIZE
        ):
            prev.chunk_text = prev.chunk_text + "\n\n" + c.chunk_text
        else:
            merged.append(c)
    chunks[:] = merged


# ── 渲染辅助 ───────────────────────────────────────────

def _block_text(b: Block) -> str:
    if b.type == "text":
        return b.content or ""
    if b.type == "table" and b.table:
        if not b.table.page_segments:
            return ""
        seg = b.table.page_segments[0]
        header = _render_header(b.table.canonical_header, b.table.column_count)
        body = "\n".join("| " + " | ".join(_escape_cell(c) for c in row) + " |" for row in seg.rows)
        return header + "\n" + body
    if b.type == "image":
        return b.caption or ""
    return ""


def _breadcrumb(section_path: list[str]) -> str:
    return " > ".join(section_path)


def _escape_cell(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ")
