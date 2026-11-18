"""Writing .xlsx workbooks: one sheet per table, the header frozen and bold,
links clickable. The Code / Datasets export, missing.xlsx, saved-search and
crawl exports and the LLM rollup all go through here.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any, Sequence

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass
class Link:
    """A cell showing text and opening url."""

    url: str
    text: str = ""


def sheet_title(name: str, used: set[str]) -> str:
    title = re.sub(r"[\[\]:*?/\\]", " ", name or "Sheet")[:31].strip() or "Sheet"
    while title in used:
        title = (title[:28] + f" {len(used) + 1}")[:31]
    used.add(title)
    return title


def cell_value(value: Any) -> Any:
    """What a cell can hold: text (cut to Excel's limit), numbers, or nothing."""
    if isinstance(value, Link):
        return (value.text or value.url)[:32000]
    if value is None or isinstance(value, bool):
        return "" if value is None else ("yes" if value else "")
    if isinstance(value, (int, float)):
        return value
    return str(value)[:32000]


def workbook(sheets: Sequence[tuple[str, Sequence[str], Sequence[Sequence[Any]]]]) -> bytes:
    """(name, header, rows) per sheet -> the .xlsx file. A cell that is a Link,
    or text that is a bare http(s) URL, becomes a hyperlink; text starting
    with "=" stays text, never a formula."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    book = Workbook()
    book.remove(book.active)
    used: set[str] = set()
    for name, columns, rows in sheets:
        ws = book.create_sheet(sheet_title(name, used))
        ws.append([str(c) for c in columns])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.freeze_panes = "A2"
        # Cells are written by number: ws.max_row and ws[n] look at every
        # cell, and asking them once a row made a big workbook take a minute.
        at = 1
        for row in rows:
            at += 1
            for column, value in enumerate(row, start=1):
                cell = ws.cell(row=at, column=column, value=cell_value(value))
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    cell.data_type = "s"
                url = value.url if isinstance(value, Link) else (
                    value if isinstance(value, str) and value.startswith(("http://", "https://")) and " " not in value else ""
                )
                if url:
                    cell.hyperlink = url
                    cell.style = "Hyperlink"
        for index, header in enumerate(columns, start=1):
            width = max([len(str(header))] + [len(str(cell_value(r[index - 1]))) for r in list(rows)[:500] if index - 1 < len(r) and r[index - 1] is not None])
            ws.column_dimensions[ws.cell(row=1, column=index).column_letter].width = min(max(width + 2, 6), 60)
    if not sheets:
        book.create_sheet("Empty")
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def filename(name: str, default: str = "export") -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or default


# -- missing works as rows ---------------------------------------------------------------

WORK_HEADER = ["Connections", "Title", "Year", "Journal", "DOI", "Proxy", "OA PDF", "OpenAlex", "Cited by", "In bibliographies", "Citing yours"]


def work_row(work: dict[str, Any], proxy_url: str) -> list[Any]:
    """One missing work as a missing.xlsx row: DOI / Proxy / OA links, year,
    journal and connections (the old workbook's columns, plus journal)."""
    doi = work.get("doi") or ""
    return [
        work.get("conn", 0),
        work.get("title") or work.get("wid"),
        work.get("year"),
        work.get("journal") or "",
        Link("https://doi.org/" + doi, doi) if doi else "",
        Link(proxy_url.replace("{doi}", doi), "proxy") if doi and proxy_url else "",
        Link(work["oa_pdf"], "pdf") if work.get("oa_pdf") else "",
        Link("https://openalex.org/" + work["wid"], work["wid"]),
        work.get("cited_by") or 0,
        work.get("lib_cites") or 0,
        work.get("cites_lib") or 0,
    ]


AUTHOR_HEADER = ["Connections", "Papers", "Author", "ORCID", "OpenAlex"]


def author_row(author: dict[str, Any]) -> list[Any]:
    orcid = author.get("orcid") or ""
    return [
        author.get("lib_cites", 0), author.get("papers", 0), author.get("name") or author.get("openalex"),
        Link("https://orcid.org/" + orcid, orcid) if orcid else "",
        Link("https://openalex.org/" + author["openalex"], author["openalex"]),
    ]


def missing_workbook(pool: Any, searches: Any, skipped: set[str], proxy_url: str, top: int = 1000) -> bytes:
    """The old `prma missing` workbook, from the live pool: Top N by
    connections, Newest, Cited-by, the top authors, and one sheet per saved
    search (its matches by connections, at most top)."""
    sheets: list[tuple[str, Sequence[str], Sequence[Sequence[Any]]]] = [
        (f"Top {top} by connections", WORK_HEADER, [work_row(w, proxy_url) for w in pool.ranked("conn", top, skipped)]),
        (f"Top {top} newest", WORK_HEADER, [work_row(w, proxy_url) for w in pool.ranked("newest", top, skipped)]),
        (f"Top {top} cited-by", WORK_HEADER, [work_row(w, proxy_url) for w in pool.ranked("cited_by", top, skipped)]),
    ]
    authors = pool.authors(skipped)
    sheets.append((f"Top {len(authors)} authors", AUTHOR_HEADER, [author_row(a) for a in authors]))
    if searches is not None:
        cache: dict[str, set[int]] = {}
        for search in searches.all():
            rows, _, _ = searches.run_missing(search, top, cache=cache)
            sheets.append((search["name"], WORK_HEADER, [work_row(w, proxy_url) for w in rows]))
    return workbook(sheets)
