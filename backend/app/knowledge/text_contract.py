"""文档数据契约: normalize(递归清 Document 树) + validate_chunks(embedding 前 fail fast) + validate_embeddings。

Why 独立模块: NUL/surrogate/NaN 等脏字符来源多样(parser/VL/PDF CID 映射), 不在各个 parser
分散处理, 统一在 ingestion post_process 后 chunk 前一层规范化, 保证 embedding 输入 = 落库文本。
Why 保守: 只处理真正破坏 PostgreSQL/pgvector 契约的(NUL 删/surrogate 替换/NaN 拒绝),
不动控制字符/零宽/NFKC/全角/空白(会破坏中文标点/表格/代码/公式/emoji)。
"""

from __future__ import annotations

import json
import math

from app.knowledge.document_models import Block, Document, Section

# ── normalize: 递归清 Document 树 ──────────────────────


def normalize_document_text(doc: Document) -> None:
    """递归规范化 Document 树的所有文本字段(原地改)。

    处理: Section.title / Block.content / Block.caption / Table header+cells。
    策略保守: 只删 NUL(\\x00) + 替换孤立 surrogate(\\uD800-\\uDFFF → \\uFFFD)。
    Why chunk 前规范化: embedding 输入 = 落库文本(一致); INSERT 后清洗导致向量/DB 不一致。
    """
    _normalize_section(doc.root)


def _normalize_section(sec: Section) -> None:
    if sec.title:
        sec.title = _clean_text(sec.title)
    for b in sec.blocks:
        _normalize_block(b)
    for child in sec.children:
        _normalize_section(child)


def _normalize_block(b: Block) -> None:
    if b.content:
        b.content = _clean_text(b.content)
    if b.caption:
        b.caption = _clean_text(b.caption)
    if b.table:
        b.table.canonical_header = [
            [_clean_text(c) for c in row] for row in b.table.canonical_header
        ]
        for seg in b.table.page_segments:
            seg.rows = [[_clean_text(c) for c in row] for row in seg.rows]


def _clean_text(text: str) -> str:
    """删除 NUL + 替换孤立 surrogate。其他字符不动。

    Why 只处理这两种: NUL 破坏 PostgreSQL text 插入; 孤立 surrogate 破坏 UTF-8 编码。
    其他控制字符(制表符/换行/零宽)可能是有意义的格式, 不碰。
    """
    if "\x00" in text:
        text = text.replace("\x00", "")
    # 孤立 surrogate(U+D800–U+DFFF) → U+FFFD(替换字符)
    if any("\ud800" <= ch <= "\udfff" for ch in text):
        text = "".join(
            "�" if "\ud800" <= ch <= "\udfff" else ch for ch in text
        )
    return text


# ── validate_chunks: chunk 后 embedding 前 fail fast ────


class InvalidChunkText(Exception):
    """chunk_text 含非法字符(NUL/surrogate)或为空。"""


class InvalidChunkMeta(Exception):
    """chunk.meta JSON 序列化失败(含 NaN/Infinity)。"""


def validate_chunks(chunks: list) -> None:
    """embedding 前校验 chunks(只读, 不修改)。失败 raise, 不浪费 embedding 成本。

    Why embedding 前而非 INSERT 前: NUL 在 embedding 不报错但 INSERT 报错;
    embedding 前校验省整份文件的 embedding 成本。
    """
    for i, chunk in enumerate(chunks):
        text = chunk.chunk_text
        if not text or not text.strip():
            raise InvalidChunkText(
                f"chunk[{i}] chunk_text 为空(规范化后文档无有效内容)"
            )
        if "\x00" in text:
            raise InvalidChunkText(
                f"chunk[{i}] chunk_text 含 NUL(normalize 遗漏?)"
            )
        if any("\ud800" <= ch <= "\udfff" for ch in text):
            raise InvalidChunkText(
                f"chunk[{i}] chunk_text 含孤立 surrogate(normalize 遗漏?)"
            )
        # meta JSON 严格序列化(allow_nan=False 防 NaN/Infinity 进 jsonb)
        try:
            json.dumps(chunk.meta, ensure_ascii=False, allow_nan=False)
        except (ValueError, OverflowError) as e:
            raise InvalidChunkMeta(
                f"chunk[{i}] meta JSON 序列化失败: {e}"
            ) from e


# ── validate_embeddings: 外部输入不信任 ─────────────────


class InvalidEmbedding(Exception):
    """embedding 返回含 NaN/Infinity 或非数字。"""


def validate_embeddings(embeddings: list[list[float]], expected_count: int) -> None:
    """校验 embedding API 返回的向量(数字/有限值/数量)。

    Why: API 返回 NaN/Infinity 会破坏 pgvector; 外部系统返回不信任。
    """
    if len(embeddings) != expected_count:
        raise InvalidEmbedding(
            f"embedding 数量 {len(embeddings)} != chunks {expected_count}"
        )
    for i, emb in enumerate(embeddings):
        for j, v in enumerate(emb):
            if not isinstance(v, (int, float)):
                raise InvalidEmbedding(
                    f"embedding[{i}][{j}] 非数字: {type(v).__name__}"
                )
            if math.isnan(v) or math.isinf(v):
                raise InvalidEmbedding(
                    f"embedding[{i}][{j}] {'NaN' if math.isnan(v) else 'Infinity'}"
                )
