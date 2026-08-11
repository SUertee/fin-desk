"""用户文档解析与切片的数据模型。

Document → Section(标题树) → Block(text/table/image 叶子)
切片消费这棵树产出 Chunk(chunk_text + meta)。
纯数据类, 不含解析/embed/存库逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TablePageSegment:
    """表格按物理页分区(跨页表的每页一段)。切片按段切, 不跨页产 chunk。"""
    page: int | None                   # 物理页(PDF/PPT 有, Word/MD/TXT=None)
    rows: list[list[str]]             # 该页的数据行


@dataclass
class Table:
    """结构化表格(不只 markdown)。切片直接消费 page_segments, 不反解析 markdown。

    Why 保留结构化: 大表切片按行切每 chunk 带表头, 反解析 markdown 会错(转义/多行/合并)。
    Why page_segments: 跨页表按页分区, 切片不跨页产 chunk(meta.page 诚实指向数据所在页)。
    Why canonical_header 未转义: 定一处转义(chunker _escape_cell 渲染时), 避免 models 已转义 + chunker 又转义的双转义。
    """
    table_id: str
    canonical_header: list[list[str]]   # 未转义原文(chunker 渲染时统一 _escape_cell)
    column_count: int
    page_segments: list[TablePageSegment]   # 按页分区(跨页表多段, 单页一段)


@dataclass
class Block:
    """叶子内容块。type 决定哪个字段有值。"""
    type: Literal["text", "table", "image"]
    content: str | None = None         # type=text: 段落文本
    table: Table | None = None         # type=table: 结构化表
    image_oss_key: str | None = None   # type=image: 私有桶 oss_key(未签名访问不了, 访问走 presign 实时签)
    caption: str | None = None         # type=image: VL 生成的描述
    page: int | None = None            # 物理页(PDF/PPT 有, Word/MD/TXT=None)
    image_bytes: bytes | None = None   # type=image: 临时(parser→post_process 运输), post_process 后清


@dataclass
class Section:
    """标题节点。level=0 是虚拟根(synthetic), 承载无标题/前言/层级跳跃。"""
    level: int                         # 0=虚拟根, 1=H1, 2=H2...
    title: str | None                  # 虚拟根 None
    synthetic: bool = False            # 虚拟根标记(不进 section_path)
    page: int | None = None
    blocks: list[Block] = field(default_factory=list)
    children: list["Section"] = field(default_factory=list)


@dataclass
class Document:
    """解析产物。root 是虚拟根(前言 + 真实 H1 children)。"""
    root: Section


@dataclass
class Chunk:
    """切片产物。chunk_text 是 embed 源(含 breadcrumb), meta 是不 embed 的元数据。"""
    chunk_text: str
    meta: dict


@dataclass
class TextFragment:
    """B 方案中间结构: 纯正文(不含 breadcrumb), 延迟渲染。

    Why 延迟渲染: 当前 _split_text 提前加 breadcrumb 焊死, 跨 path 合并重复标题/算错长度;
    fragment 只存纯 payload, pack 组合后最后统一渲染 breadcrumb + 局部 ##。
    """
    payload: str                       # 纯正文(段落原文, 不含标题)
    path: list[str]                    # section_path(如 ["请假制度","病假"])
    level: int                         # 真实 section.level(局部标题用, 不用 path 推)
    page: int | None                   # 物理页
