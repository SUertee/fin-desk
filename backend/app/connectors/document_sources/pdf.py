"""PDF parser: pymupdf 读 PDF → Document（三阶段 extract/enrich/finalize）。

Why get_text("dict") 而非 "text": 要 bbox(表格去重/页眉页脚判定) + size(标题启发式),
纯文本拿不到。find_tables() 内置表格检测(1.23+), 比手写省一大半且制度类够用。

四条正确性:
- 扫描件(文本量少 + 有图) → raise ScanPdfUnsupported(早退, 避免白做后续)
- 表格文字去重: text atom 中心落在 table bbox 内 → 跳过(pymupdf text/table 区域重叠)
- 页眉页脚: 跨 >=3 页重复的顶/底带文本 → 过滤(归一化去数字容忍页码差异)
- 跨页表: 相邻页同列数 + 后者首行非表头 → 合并 page_segments(保守, 宁可不合)

三阶段(parser 保持纯, VL I/O 隔离在 enrich):
- extract_pdf(content) → PdfDraft: 纯, open doc + atoms(含 atom_id) + body_size + hf_set
  + page_rects + layout_confidence_by_page(双栏检测, 独立于 heading)
- enrich_pdf_layout(draft, content, vision) → EnrichResult: worker 调 VL, 渲染低 layout_confidence
  页 → VL 返回阅读顺序 + 标题角色; 返 patch + 诊断(attempted/patched/failed); 失败页回退启发式
- finalize_pdf(draft, patch=None) → Document: 纯, apply patch(重排 + heading_role) → 主循环产 Block

VL 只 patch(不动原文/bbox/size/table): PyMuPDF 负责结构化原文, VL 只返回 atom_id 的阅读
顺序 + heading 层级覆盖; patch 校验失败回退启发式(不接整页 atom, 避免丢结构)。
parse_pdf(content) = finalize_pdf(extract_pdf(content)) 向后兼容 factory(无 VL)。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Literal

from app.connectors.document_sources._tables import make_table, normalize_table_header
from app.knowledge.document_models import (
    Block,
    Document,
    Section,
    TablePageSegment,
)


class ScanPdfUnsupported(Exception):
    """扫描件 PDF(无文本层), 启发式无法处理。"""


class UnsupportedDocumentType(Exception):
    """不支持的文件格式（document_sources 兼容 re-export）。"""


# ── 参数(冒烟后调) ───────────────────────────────────────

SCAN_TEXT_MIN = 20           # 单页文本 >= 此字符数视为"有文本"(扫描件检测)
SCAN_TEXT_PAGE_RATIO = 0.3   # 扫描件页占比 >= 此值 → 判扫描件 PDF
HEADING_SIZE_H1 = 1.35       # 无编号时字号 >= 正文*此值 → H1(制度章节标题常为正文1.4-1.5×)
HEADING_SIZE_H2 = 1.15       # 无编号时字号 >= 正文*此值 → H2
HEADING_MAX_LEN = 40         # 无编号标题候选的最大长度(防加粗正文误判)
TABLE_COL_NONEMPTY_RATIO = 0.5  # 有效表格列: data 非空率 >= 此值
HF_BAND_RATIO = 0.08         # 顶/底带占页高比例(页眉页脚扫描区)
HF_REPEAT_PAGES = 3          # 跨 >= 此页重复才算页眉页脚
LAYOUT_CONFIDENCE_THRESHOLD = 0.5  # layout_confidence < 此值的页调 VL(enrich 用)
LAYOUT_DUAL_COLUMN_OVERLAP = 0.3   # 左右栏纵向重叠 > 页高*此值 → 双栏
VL_PROMPT_VERSION = "v1"   # prompt 版本(缓存键, 改 prompt 升版本)
VL_PAGE_PROMPT = """这是文档某页的截图(红框 + ID 标注了文本/表格块)。
下面列出该页的有效块(已过滤页眉页脚和表内冗余), 每个带 id + 类型 + 归一化 bbox + 文本片段:

{atom_list}

请按正确的阅读顺序排列这些 id(双栏: 左栏从上到下读, 再右栏从上到下; 表格按首行所在位置参与排序)。
可选: 标注标题角色(1=H1 章节标题, 2=H2, 3=H3, "body"=明确正文非标题)。
只返回 JSON, 格式: {{"semantic_order": ["pX-aY", ...], "heading_roles": {{"pX-aY": 1}}}}
"""


# ── 编号模式(制度文档标题层级约定) ──────────────────────

_H1_PATTERNS = [
    re.compile(r'^第[一二三四五六七八九十百千0-9]+[章节编条部分篇]'),
    re.compile(r'^[一二三四五六七八九十]+[、.．]'),
]
# H3 先于 H2 判(比 "1." 更具体): "1.1 xxx"; (?!\d) 防 "1.10" 被 "1.1" 截断匹配
_H3_PATTERN = re.compile(r'^\d+[.．]\d+(?!\d)')
_H2_PATTERNS = [
    re.compile(r'^[（(][一二三四五六七八九十0-9]+[)）]'),
    re.compile(r'^\d+[、.．]'),
]


# ── _PageAtom: 有序流原子(内部中间结构) ─────────────────

@dataclass
class _PageAtom:
    """单页内的有序内容原子。"""
    page: int
    kind: Literal["text", "table", "image"]
    bbox: tuple[float, float, float, float]
    atom_id: str                       # "p{page}-a{idx}", _collect_atoms 赋, VL patch 引用
    text: str | None = None
    size: float | None = None
    rows: list[list[str]] | None = None
    columns: int | None = None
    image_bytes: bytes | None = None   # kind=image: 原始图字节(parser→post_process 运输)
    heading_role: int | str | None = None   # VL 覆盖: int(1/2/3 标题级别) / "body"(强制正文) / None(走启发式)


# ── PdfDraft + LayoutPatch(三阶段契约)──────────────────

@dataclass
class PdfDraft:
    """extract_pdf 产物: parser 原始读取(无 VL patch)。finalize_pdf 消费。"""
    n_pages: int
    atoms_by_page: dict[int, list[_PageAtom]]
    body_size: float
    hf_set: set[str]
    page_rects: dict[int, tuple[float, float, float, float]]
    layout_confidence_by_page: dict[int, float]


@dataclass
class LayoutPatch:
    """VL 补判 patch: 只改阅读顺序 + 标题角色, 不动原文/bbox/size/table rows。"""
    semantic_order: dict[int, list[str]]          # page → [atom_id] 阅读顺序(text+table)
    heading_roles: dict[str, int | str]           # atom_id → 1/2/3 标题 / "body" 强制正文
    prompt_version: str = ""                       # prompt 版本(缓存键)


@dataclass
class EnrichResult:
    """enrich_pdf_layout 产物: patch + 诊断。"""
    patch: LayoutPatch | None
    attempted: list[int]                  # 调了 VL 的页
    patched: list[int]                    # 成功 patch 的页
    failed: list[tuple[int, str]]         # 失败页 + 原因


# ── 主入口(向后兼容 = finalize(extract(content)))──────

def parse_pdf(content: bytes) -> Document:
    """factory 入口, 无 VL patch。worker 要 VL 时直接调 extract/enrich/finalize 三阶段。"""
    return finalize_pdf(extract_pdf(content))


# ── 阶段1: extract(纯)──────────────────────────────────

def extract_pdf(content: bytes) -> PdfDraft:
    """纯: open doc → atoms(含 atom_id) + body_size + hf_set + page_rects + layout_confidence。"""
    import fitz

    doc = fitz.open(stream=content, filetype="pdf")
    try:
        if _detect_scan_pdf(doc):
            raise ScanPdfUnsupported("扫描件 PDF(无文本层)暂不支持, 请提供文字版 PDF")
        n = len(doc)
        atoms_by_page = {pno: _collect_atoms(doc, pno) for pno in range(1, n + 1)}
        all_atoms = [a for atoms in atoms_by_page.values() for a in atoms]
        body_size = _body_font_size(all_atoms)
        hf_set = _collect_header_footer(doc, atoms_by_page)
        page_rects = {pno: tuple(doc[pno - 1].rect) for pno in range(1, n + 1)}
        layout_confidence_by_page = {
            pno: _layout_confidence(atoms_by_page[pno], page_rects[pno])
            for pno in range(1, n + 1)
        }
        return PdfDraft(
            n_pages=n, atoms_by_page=atoms_by_page, body_size=body_size,
            hf_set=hf_set, page_rects=page_rects,
            layout_confidence_by_page=layout_confidence_by_page,
        )
    finally:
        doc.close()


# ── 阶段2: enrich(worker 调 VL)─────────────────────────

def enrich_pdf_layout(draft: PdfDraft, content: bytes, vision) -> EnrichResult:
    """worker 调 VL 补判低 layout_confidence 页 → EnrichResult(patch + 诊断)。

    低 confidence(< LAYOUT_CONFIDENCE_THRESHOLD) + 无 image 的页 → 渲染+bbox 叠加 → VL →
    _parse_vl_json 校验 → patch; 失败(网络/HTTP/渲染/JSON) → failed(按页回退, 其他页继续)。
    image 页 skip; 高 confidence 不调 VL。
    """
    import fitz
    semantic_order: dict[int, list[str]] = {}
    heading_roles: dict[str, int | str] = {}
    attempted: list[int] = []
    patched: list[int] = []
    failed: list[tuple[int, str]] = []
    doc = fitz.open(stream=content, filetype="pdf")
    try:
        for pno in range(1, draft.n_pages + 1):
            if draft.layout_confidence_by_page[pno] >= LAYOUT_CONFIDENCE_THRESHOLD:
                continue
            if any(a.kind == "image" for a in draft.atoms_by_page[pno]):
                continue   # image 页 skip(bbox 伪造)
            effective = _filter_atoms(draft, pno)
            if not effective:
                continue
            attempted.append(pno)
            try:
                png = _render_with_overlays(doc, pno, effective)
                atom_list = _format_atom_list(effective, draft.page_rects[pno])
                prompt = VL_PAGE_PROMPT.format(atom_list=atom_list)
                observation = vision.describe_image(png, "image/png", prompt=prompt)
                raw = observation.caption
                parsed = _parse_vl_json(raw, effective)
                if parsed is None:
                    failed.append((pno, "json invalid"))
                    continue
                semantic_order[pno] = parsed[0]
                heading_roles.update(parsed[1])
                patched.append(pno)
            except Exception as e:
                failed.append((pno, str(e)))
    finally:
        doc.close()
    patch = LayoutPatch(
        semantic_order=semantic_order, heading_roles=heading_roles,
        prompt_version=VL_PROMPT_VERSION,
    ) if semantic_order else None
    return EnrichResult(patch=patch, attempted=attempted, patched=patched, failed=failed)


def _filter_atoms(draft: PdfDraft, pno: int) -> list[_PageAtom]:
    """过滤 HF + 表内冗余, 返真正进 Document 的 atoms(finalize + enrich 共用)。"""
    atoms = draft.atoms_by_page[pno]
    table_atoms = [a for a in atoms if a.kind == "table"]
    effective: list[_PageAtom] = []
    for a in atoms:
        if a.kind == "text":
            if _normalize_hf(a.text) in draft.hf_set:
                continue
            is_heading = _heading_level(a.text, a.size, draft.body_size) is not None
            if not is_heading and _in_any_table(a, table_atoms):
                continue
        effective.append(a)
    return effective


def _format_atom_list(effective: list[_PageAtom], page_rect: tuple) -> str:
    """effective atoms → VL prompt 的 atom 列表(id + kind + 归一化 bbox + 文本片段)。"""
    lines = []
    for a in effective:
        if a.kind == "image":
            continue
        nx0 = a.bbox[0] / page_rect[2] if page_rect[2] else 0
        ny0 = a.bbox[1] / page_rect[3] if page_rect[3] else 0
        nx1 = a.bbox[2] / page_rect[2] if page_rect[2] else 0
        ny1 = a.bbox[3] / page_rect[3] if page_rect[3] else 0
        text_excerpt = (a.text or "")[:50]
        lines.append(
            f"[{a.atom_id}] {a.kind} bbox=({nx0:.2f},{ny0:.2f},{nx1:.2f},{ny1:.2f}) {text_excerpt}"
        )
    return "\n".join(lines)


def _render_with_overlays(doc, pno: int, effective: list[_PageAtom]) -> bytes:
    """渲染页(2x) + 画 atom bbox 红框 + atom_id 标注 → PNG bytes。"""
    import fitz
    page = doc[pno - 1]
    for a in effective:
        if a.kind == "image":
            continue
        rect = fitz.Rect(a.bbox)
        page.draw_rect(rect, color=(1, 0, 0), width=0.5)
        page.insert_text(
            (rect.x0, max(0, rect.y0 - 2)), a.atom_id, fontsize=6, color=(1, 0, 0),
        )
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    return pix.tobytes("png")


def _parse_vl_json(
    raw: str, effective: list[_PageAtom],
) -> tuple[list[str], dict[str, int | str]] | None:
    """解析 VL JSON → (semantic_order, heading_roles); 校验失败返 None。"""
    import json
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group())
    except Exception:
        return None
    order = data.get("semantic_order") or []
    roles = data.get("heading_roles") or {}
    valid_ids = {a.atom_id for a in effective}
    if len(order) != len(effective) or len(set(order)) != len(order):
        return None
    if not all(aid in valid_ids for aid in order):
        return None
    clean_roles: dict[str, int | str] = {}
    for k, v in roles.items():
        if k not in valid_ids:
            continue
        if isinstance(v, int) and v in (1, 2, 3):
            clean_roles[k] = v
        elif v == "body":
            clean_roles[k] = "body"
    return order, clean_roles


# ── 阶段3: finalize(纯, apply patch → Document)─────────

def finalize_pdf(draft: PdfDraft, patch: LayoutPatch | None = None) -> Document:
    """纯: _filter_atoms 过滤(和 enrich 同源) → apply patch(重排 + heading_role) → 主循环产 Block。"""
    root = Section(level=0, title=None, synthetic=True)
    stack: list[Section] = [root]
    page_tables: dict[int, list[tuple[Block, Section]]] = {}

    for pno in range(1, draft.n_pages + 1):
        effective = _filter_atoms(draft, pno)
        atoms = _apply_layout_patch(effective, pno, patch)
        for a in atoms:
            if a.kind == "text":
                role = a.heading_role
                if role == "body":
                    level = None
                elif isinstance(role, int):
                    level = role
                else:
                    level = _heading_level(a.text, a.size, draft.body_size)
                if level is not None:
                    _push_heading(stack, level, a.text.strip(), pno)
                else:
                    stack[-1].blocks.append(
                        Block(type="text", content=a.text.strip(), page=pno)
                    )
            elif a.kind == "image":
                stack[-1].blocks.append(Block(
                    type="image", image_bytes=a.image_bytes, page=pno,
                ))
            else:   # table
                rows = a.rows or []
                if len(rows) < 2:
                    continue
                table = make_table(rows, f"pdf_table_{pno}_{id(a)}", pno, a.columns)
                tbl_block = Block(type="table", table=table, page=pno)
                stack[-1].blocks.append(tbl_block)
                page_tables.setdefault(pno, []).append((tbl_block, stack[-1]))

    _merge_cross_page_tables(page_tables)
    return Document(root=root)


def _apply_layout_patch(
    atoms: list[_PageAtom], pno: int, patch: LayoutPatch | None,
) -> list[_PageAtom]:
    """apply patch 到该页 atoms(atomic: 校验全过才 apply, 不改 draft 原 atoms)。"""
    if patch is None:
        return atoms
    if pno in patch.semantic_order:
        order = patch.semantic_order[pno]
        atom_by_id = {a.atom_id: a for a in atoms}
        if (len(order) != len(atoms)
                or len(set(order)) != len(order)
                or not all(aid in atom_by_id for aid in order)):
            return atoms
        new_atoms = [atom_by_id[aid] for aid in order]
    else:
        new_atoms = list(atoms)
    result = []
    for a in new_atoms:
        role = patch.heading_roles.get(a.atom_id)
        result.append(replace(a, heading_role=role) if role is not None else a)
    return result


# ── 扫描件检测 ──────────────────────────────────────────

def _detect_scan_pdf(doc) -> bool:
    """扫描件页("文本量少 + 有图")占比 >= SCAN_TEXT_PAGE_RATIO → 判扫描件 PDF。"""
    n = len(doc)
    if n == 0:
        return False
    scan_pages = 0
    for page in doc:
        text_len = len(page.get_text("text").strip())
        has_image = any(
            b.get("type") == 1
            for b in page.get_text("dict").get("blocks", [])
        )
        if text_len < SCAN_TEXT_MIN and has_image:
            scan_pages += 1
    return scan_pages / n >= SCAN_TEXT_PAGE_RATIO


# ── 原子收集 ────────────────────────────────────────────

def _collect_atoms(doc, page_no: int) -> list[_PageAtom]:
    """单页 → 有序 atoms(table 先于 text 收集, 统一按 y0,x0 排序; atom_id 收集时赋)。"""
    import fitz
    page = doc[page_no - 1]
    atoms: list[_PageAtom] = []
    idx = 0

    for tbl in page.find_tables().tables:
        rows = [[(c or "").strip() for c in row] for row in tbl.extract()]
        if len(rows) < 2:
            continue
        rows = normalize_table_header(rows)
        if len(rows) < 2 or not _is_valid_table(rows):
            continue
        atoms.append(_PageAtom(
            page=page_no, kind="table", bbox=tuple(tbl.bbox),
            atom_id=f"p{page_no}-a{idx}", rows=rows,
            columns=max(len(r) for r in rows),
        ))
        idx += 1

    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:   # image block 无 bytes 不用(图片走 get_images)
            continue
        for frag in _split_block_by_size(block):
            if not frag["text"].strip():
                continue
            atoms.append(_PageAtom(
                page=page_no, kind="text", bbox=frag["bbox"],
                atom_id=f"p{page_no}-a{idx}",
                text=frag["text"], size=frag["size"],
            ))
            idx += 1

    rect = page.rect
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.n - pix.alpha >= 4:   # CMYK/特殊色彩空间 → RGB
                pix = fitz.Pixmap(fitz.csRGB, pix)
            img_bytes = pix.tobytes("png")
        except Exception:
            continue
        atoms.append(_PageAtom(
            page=page_no, kind="image",
            bbox=(0.0, rect.y1, 0.0, rect.y1),
            atom_id=f"p{page_no}-a{idx}",
            image_bytes=img_bytes,
        ))
        idx += 1

    atoms.sort(key=lambda a: (a.bbox[3] if a.kind == "table" else a.bbox[1], a.bbox[0]))
    return atoms


def _split_block_by_size(block: dict) -> list[dict]:
    """block 内按字号拆: 连续同字号 line 合成一个片段。"""
    frags: list[dict] = []
    cur_lines: list[tuple[str, tuple]] = []
    cur_size: float | None = None
    for line in block.get("lines", []):
        line_size = _dominant_size(line)
        line_text = "".join(span.get("text", "") for span in line.get("spans", []))
        line_bbox = tuple(line.get("bbox", (0.0, 0.0, 0.0, 0.0)))
        if cur_size is None or line_size is None or line_size == cur_size:
            if cur_size is None:
                cur_size = line_size
            cur_lines.append((line_text, line_bbox))
        else:
            frags.append(_make_frag(cur_lines, cur_size))
            cur_size = line_size
            cur_lines = [(line_text, line_bbox)]
    if cur_lines:
        frags.append(_make_frag(cur_lines, cur_size))
    return frags


def _make_frag(lines: list[tuple[str, tuple]], size: float | None) -> dict:
    text = "\n".join(t for t, _ in lines).strip()
    return {"text": text, "size": size, "bbox": _union_bbox([b for _, b in lines])}


def _union_bbox(bboxes: list[tuple]) -> tuple:
    if not bboxes:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(b[0] for b in bboxes), min(b[1] for b in bboxes),
        max(b[2] for b in bboxes), max(b[3] for b in bboxes),
    )


def _dominant_size(obj: dict) -> float | None:
    """obj 是 line dict(有 spans) 或 block dict(有 lines) → span 字号众数。None 表无字号。"""
    spans = obj.get("spans") or [
        s for line in obj.get("lines", []) for s in line.get("spans", [])
    ]
    sizes = [round(s.get("size", 0), 1) for s in spans if s.get("size")]
    if not sizes:
        return None
    return Counter(sizes).most_common(1)[0][0]


# ── 正文字号 + 标题判定 ─────────────────────────────────

def _body_font_size(atoms: list[_PageAtom]) -> float:
    """正文字号: 按文本字符数加权的字号众数。"""
    weighted: Counter[float] = Counter()
    for a in atoms:
        if a.kind == "text" and a.size:
            weighted[round(a.size, 1)] += len(a.text or "")
    if not weighted:
        return 12.0
    return weighted.most_common(1)[0][0]


def _heading_level(
    text: str, size: float | None, body_size: float
) -> int | None:
    """标题等级: 编号模式 + 字号联合判定; 无编号看字号(短文本 + 大字号)。"""
    t = text.strip()
    if not t:
        return None
    heading_size_ok = bool(
        size and body_size and size >= body_size * HEADING_SIZE_H2
    )
    if heading_size_ok:
        for pat in _H1_PATTERNS:
            if pat.match(t):
                return 1
        if _H3_PATTERN.match(t):
            return 3
        for pat in _H2_PATTERNS:
            if pat.match(t):
                return 2
    if size and body_size and len(t) <= HEADING_MAX_LEN:
        if size >= body_size * HEADING_SIZE_H1:
            return 1
        if size >= body_size * HEADING_SIZE_H2:
            return 2
    return None


def _push_heading(
    stack: list[Section], level: int, title: str, page: int
) -> None:
    """标题入栈: pop 到 level 严格小于当前, append child, push 新 section。"""
    title = " ".join(title.split())
    new_sec = Section(level=level, title=title, page=page)
    while len(stack) > 1 and stack[-1].level >= level:
        stack.pop()
    stack[-1].children.append(new_sec)
    stack.append(new_sec)


# ── 表格文字去重 ────────────────────────────────────────

def _in_any_table(atom: _PageAtom, tables: list[_PageAtom]) -> bool:
    """text atom 中心落在任一 table bbox 内 → 文字已被表格消费, 跳过。"""
    cx = (atom.bbox[0] + atom.bbox[2]) / 2
    cy = (atom.bbox[1] + atom.bbox[3]) / 2
    for t in tables:
        tx0, ty0, tx1, ty1 = t.bbox
        if tx0 <= cx <= tx1 and ty0 <= cy <= ty1:
            return True
    return False


# ── 页眉页脚过滤 ────────────────────────────────────────

def _normalize_hf(text: str) -> str:
    """页眉页脚归一化: 去数字(容忍页码每页不同)。"""
    return re.sub(r"\d+", "", text or "").strip()


def _collect_header_footer(
    doc, atoms_by_page: dict[int, list[_PageAtom]]
) -> set[str]:
    """跨 >= HF_REPEAT_PAGES 页重复的顶/底带文本 → 页眉页脚集合。"""
    candidates: Counter[str] = Counter()
    for pno, atoms in atoms_by_page.items():
        rect = doc[pno - 1].rect
        band = (rect.y1 - rect.y0) * HF_BAND_RATIO
        top_y, bot_y = rect.y0 + band, rect.y1 - band
        for a in atoms:
            if a.kind != "text":
                continue
            cy = (a.bbox[1] + a.bbox[3]) / 2
            if cy < top_y or cy > bot_y:
                norm = _normalize_hf(a.text)
                if norm:
                    candidates[norm] += 1
    return {t for t, n in candidates.items() if n >= HF_REPEAT_PAGES}


# ── 表格有效性(过滤 find_tables 误检)────────────────────

def _is_valid_table(rows: list[list[str]]) -> bool:
    """有效表格: data 行里非空率 >= TABLE_COL_NONEMPTY_RATIO 的列 >= 2 列。"""
    data = rows[1:]
    if not data:
        return False
    ncols = max(len(r) for r in rows)
    col_nonempty = [0] * ncols
    for r in data:
        for k in range(ncols):
            if k < len(r) and r[k]:
                col_nonempty[k] += 1
    thr = max(1, len(data) * TABLE_COL_NONEMPTY_RATIO)
    return sum(1 for x in col_nonempty if x >= thr) >= 2


# ── 跨页表合并 ──────────────────────────────────────────

def _merge_cross_page_tables(
    page_tables: dict[int, list[tuple[Block, Section]]],
) -> None:
    """相邻页 table: 同列数 + 后者首行非表头 → 合并进前者(retained 跟踪 + 续页首行放回)。"""
    retained: dict[int, tuple[Block, Section]] = {}
    for pno in sorted(page_tables):
        cur = page_tables[pno]
        cur_first, cur_owner = cur[0]
        prev_target = retained.get(pno - 1)
        if prev_target is None:
            prev = page_tables.get(pno - 1)
            if not prev:
                retained[pno] = (cur_first, cur_owner)
                continue
            prev_target = (prev[-1][0], prev[-1][1])
        last_block, _ = prev_target
        first_block, first_owner = cur_first, cur_owner
        last_table = last_block.table
        first_table = first_block.table
        if (last_table is None or first_table is None
                or last_table.column_count != first_table.column_count
                or not first_table.page_segments
                or not first_table.page_segments[0].rows):
            retained[pno] = (cur_first, cur_owner)
            continue
        header = last_table.canonical_header[0] if last_table.canonical_header else []
        first_header_row = first_table.canonical_header[0] if first_table.canonical_header else []
        if _looks_like_header(first_header_row, header):
            retained[pno] = (cur_first, cur_owner)
            continue
        first_seg = first_table.page_segments[0]
        last_table.page_segments.append(TablePageSegment(
            page=first_seg.page,
            rows=[first_header_row] + first_seg.rows,
        ))
        first_owner.blocks.remove(first_block)
        retained[pno] = prev_target


def _looks_like_header(row: list[str], header: list[str]) -> bool:
    if not header:
        return False
    return [c.strip() for c in row] == [c.strip() for c in header]


# ── 双栏检测(版式 confidence, 独立于 heading)────────────

def _layout_confidence(atoms: list[_PageAtom], page_rect: tuple) -> float:
    """双栏检测: text atoms 左右栏各有 + 纵向重叠 > 页高*LAYOUT_DUAL_COLUMN_OVERLAP → 0.4(低)。"""
    text_atoms = [a for a in atoms if a.kind == "text"]
    if len(text_atoms) < 6:
        return 1.0
    mid_x = (page_rect[0] + page_rect[2]) / 2
    left = [a for a in text_atoms if a.bbox[2] <= mid_x]
    right = [a for a in text_atoms if a.bbox[0] >= mid_x]
    if len(left) < 3 or len(right) < 3:
        return 1.0
    left_y0 = min(a.bbox[1] for a in left)
    left_y1 = max(a.bbox[3] for a in left)
    right_y0 = min(a.bbox[1] for a in right)
    right_y1 = max(a.bbox[3] for a in right)
    overlap = min(left_y1, right_y1) - max(left_y0, right_y0)
    page_h = page_rect[3] - page_rect[1]
    if overlap > page_h * LAYOUT_DUAL_COLUMN_OVERLAP:
        return 0.4
    return 1.0
