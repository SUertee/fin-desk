"""DOCX parser: python-docx, XML-order body walk (paragraph/table/image interleaved)."""

from __future__ import annotations

from io import BytesIO

from app.connectors.document_sources._tables import make_table
from app.knowledge.document_models import Block, Document, Section


def parse_docx(content: bytes) -> Document:
    from docx import Document as DocxDocument
    from docx.oxml.ns import qn
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph

    doc = DocxDocument(BytesIO(content))
    root = Section(level=0, title=None, synthetic=True)
    stack: list[Section] = [root]

    for child in doc.element.body.iterchildren():
        tag = child.tag
        if tag == qn("w:p"):
            para = Paragraph(child, doc)
            text = para.text.strip()
            # Embedded images (w:drawing → a:blip r:embed → image part bytes)
            for blip in child.iter(qn("a:blip")):
                rId = blip.get(qn("r:embed"))
                if rId and rId in doc.part.related_parts:
                    stack[-1].blocks.append(
                        Block(type="image", image_bytes=doc.part.related_parts[rId].blob)
                    )
            if not text:
                continue
            style = (para.style.name or "").lower() if para.style else ""
            if style.startswith("heading"):
                try:
                    level = int(style.replace("heading", "").strip())
                except ValueError:
                    level = 1
                new_sec = Section(level=level, title=text)
                while len(stack) > 1 and stack[-1].level >= level:
                    stack.pop()
                stack[-1].children.append(new_sec)
                stack.append(new_sec)
            else:
                stack[-1].blocks.append(Block(type="text", content=text))
        elif tag == qn("w:tbl"):
            tbl = DocxTable(child, doc)
            rows = [[cell.text.strip() for cell in row.cells] for row in tbl.rows]
            if len(rows) < 2:
                continue
            table = make_table(rows, f"docx_table_{id(child)}", None)
            stack[-1].blocks.append(Block(type="table", table=table))
    return Document(root=root)
