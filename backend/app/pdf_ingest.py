import io
import logging
import re
from pypdf import PdfReader

logger = logging.getLogger(__name__)
PAGE_MARKER_PATTERN = re.compile(r"--- PAGE (\d+) ---\n")
TABLE_BLOCK_PATTERN = re.compile(r"(?=\[TABLE \d+\])")


def _clean_cell(value: object) -> str:
    if value is None:
        return ""
    normalized = str(value).replace("\r", "\n")
    normalized = re.sub(r"\n+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _looks_like_header(first_row: list[str], second_row: list[str] | None) -> bool:
    if not first_row:
        return False
    non_empty = [cell for cell in first_row if cell]
    if not non_empty:
        return False
    alpha_cells = sum(1 for cell in non_empty if re.search(r"[A-Za-zÄÖÜäöü]", cell))
    mostly_numeric = all(re.fullmatch(r"[\d.,\-/%]+", cell) for cell in non_empty)
    if mostly_numeric:
        return False
    if second_row:
        second_non_empty = [cell for cell in second_row if cell]
        if second_non_empty and alpha_cells >= max(1, len(non_empty) // 2):
            return True
    return alpha_cells == len(non_empty)


def _render_table(rows: list[list[object]]) -> str:
    cleaned_rows: list[list[str]] = []
    max_cols = max((len(row) for row in rows), default=0)
    if max_cols == 0:
        return ""

    for row in rows:
        cells = [_clean_cell(cell) for cell in row]
        if len(cells) < max_cols:
            cells.extend([""] * (max_cols - len(cells)))
        cleaned_rows.append(cells)

    if not cleaned_rows:
        return ""

    header = cleaned_rows[0]
    body = cleaned_rows[1:] if len(cleaned_rows) > 1 else []
    if _looks_like_header(header, body[0] if body else None):
        head_line = "| " + " | ".join(header) + " |"
        sep_line = "| " + " | ".join(["---"] * len(header)) + " |"
        body_lines = ["| " + " | ".join(row) + " |" for row in body]
        return "\n".join([head_line, sep_line, *body_lines]).strip()

    return "\n".join("\t".join(row) for row in cleaned_rows).strip()


def _extract_tables_section(content: bytes) -> tuple[str, int]:
    try:
        import pdfplumber  # type: ignore
    except Exception:
        logger.warning("pdfplumber is not available; skipping table extraction")
        return "TABLES:\n(pdfplumber unavailable)", 0

    rendered_tables: list[str] = []
    pages_with_tables = 0
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            page_tables: list[str] = []
            for table_index, table_rows in enumerate(tables, start=1):
                if not table_rows:
                    continue
                rendered = _render_table(table_rows)
                if not rendered:
                    continue
                page_tables.append(f"[TABLE {table_index}]\n{rendered}")

            if page_tables:
                pages_with_tables += 1
                rendered_tables.append(
                    f"--- PAGE {page_index} ---\n" + "\n\n".join(page_tables)
                )

    if not rendered_tables:
        return "TABLES:\n(no tables detected)", 0
    return "TABLES:\n\n" + "\n\n".join(rendered_tables), pages_with_tables


def _compute_quality_score(total_pages: int, pages_with_text: int, text_length: int) -> float:
    if total_pages <= 0:
        return 0.0
    pages_with_text_ratio = pages_with_text / total_pages
    length_score = min(1.0, text_length / 15000.0)
    score = min(1.0, 0.6 * pages_with_text_ratio + 0.4 * length_score)
    return round(score, 3)


def _extract_text_from_pdf_bytes(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    parts: list[str] = []
    pages_with_text = 0

    for i, page in enumerate(reader.pages):
        txt = (page.extract_text() or "").strip()
        if txt:
            pages_with_text += 1
        parts.append(f"\n\n--- PAGE {i+1} ---\n{txt}")

    text_part = "\n".join(parts)
    tables_section, pages_with_tables = _extract_tables_section(content)
    combined = f"{text_part}\n\n{tables_section}"

    total_pages = len(reader.pages)
    quality_score = _compute_quality_score(total_pages, pages_with_text, len(text_part))
    pages_with_text_ratio = round((pages_with_text / total_pages), 3) if total_pages else 0.0
    logger.info(
        "PDF extraction quality: score=%.3f pages=%d pages_with_text=%d pages_with_text_ratio=%.3f text_chars=%d pages_with_tables=%d",
        quality_score,
        total_pages,
        pages_with_text,
        pages_with_text_ratio,
        len(text_part),
        pages_with_tables,
    )
    return combined


def extract_text_from_pdf(path: str) -> str:
    with open(path, "rb") as f:
        return _extract_text_from_pdf_bytes(f.read())


def extract_text_from_pdf_bytes(content: bytes) -> str:
    return _extract_text_from_pdf_bytes(content)


def _chunk_text_block(text: str, max_chars: int, overlap: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
        if start < 0:
            start = 0
        if end == len(text):
            break
    return chunks


def _parse_pages(section_text: str) -> dict[int, str]:
    pages: dict[int, str] = {}
    if not section_text:
        return pages
    matches = list(PAGE_MARKER_PATTERN.finditer(section_text))
    if not matches:
        cleaned = section_text.strip()
        if cleaned:
            pages[1] = cleaned
        return pages

    for i, match in enumerate(matches):
        page_no = int(match.group(1))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
        content = section_text[start:end].strip()
        if content:
            pages[page_no] = content
    return pages


def _chunk_table_content(table_text: str, max_chars: int, overlap: int) -> list[str]:
    cleaned = (table_text or "").strip()
    if not cleaned:
        return []
    table_blocks = [b.strip() for b in TABLE_BLOCK_PATTERN.split(cleaned) if b.strip()]
    if not table_blocks:
        return _chunk_text_block(cleaned, max_chars=max_chars, overlap=overlap)

    chunks: list[str] = []
    current = "TABLES:\n"
    for block in table_blocks:
        candidate = f"{current}\n\n{block}".strip() if current.strip() else block
        if len(block) > max_chars:
            if current.strip() and current.strip() != "TABLES:":
                chunks.append(current.strip())
            chunks.extend(_chunk_text_block(block, max_chars=max_chars, overlap=overlap))
            current = "TABLES:\n"
            continue
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current.strip() and current.strip() != "TABLES:":
            chunks.append(current.strip())
        current = f"TABLES:\n\n{block}".strip()

    if current.strip() and current.strip() != "TABLES:":
        chunks.append(current.strip())
    return chunks


def simple_chunk(text: str, max_chars: int = 1200, overlap: int = 150, with_metadata: bool = False):
    text = (text or "").strip()
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if overlap >= max_chars:
        overlap = max_chars // 4

    if not text:
        return []

    tables_split = text.split("\n\nTABLES:", 1)
    body_text = tables_split[0]
    tables_text = tables_split[1] if len(tables_split) > 1 else ""

    body_pages = _parse_pages(body_text)
    table_pages = _parse_pages(tables_text)
    page_numbers = sorted(set(body_pages.keys()) | set(table_pages.keys()))

    chunk_records: list[dict] = []
    global_index = 0
    for page_no in page_numbers:
        page_body = body_pages.get(page_no, "")
        page_tables = table_pages.get(page_no, "")

        page_chunks = _chunk_text_block(page_body, max_chars=max_chars, overlap=overlap)
        table_chunks = _chunk_table_content(page_tables, max_chars=max_chars, overlap=overlap)

        if table_chunks and page_chunks:
            if len(page_chunks[-1]) + 2 + len(table_chunks[0]) <= max_chars:
                page_chunks[-1] = f"{page_chunks[-1]}\n\n{table_chunks[0]}"
                table_chunks = table_chunks[1:]

        combined_page_chunks = [*page_chunks, *table_chunks]
        if not combined_page_chunks:
            continue

        for page_chunk_index, chunk_text in enumerate(combined_page_chunks):
            chunk_records.append(
                {
                    "text": chunk_text,
                    "page": page_no,
                    "page_chunk_index": page_chunk_index,
                    "global_chunk_index": global_index,
                }
            )
            global_index += 1

    if with_metadata:
        return chunk_records
    return [record["text"] for record in chunk_records]
