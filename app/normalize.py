from __future__ import annotations

import re


def _normalize_header(header: str) -> str:
    return re.sub(r"\s+", "", header.strip().lower())


def parse_markdown_table(markdown: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in markdown.splitlines() if "|" in line]
    if len(lines) < 2:
        return []
    header_cells = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < len(header_cells):
            cells += [""] * (len(header_cells) - len(cells))
        rows.append({header_cells[idx]: cells[idx] for idx in range(len(header_cells))})
    return rows
