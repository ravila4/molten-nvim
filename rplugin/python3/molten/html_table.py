"""Convert HTML tables (such as the pandas DataFrame repr) into GFM pipe tables."""

from html.parser import HTMLParser
from typing import List, Optional, Tuple

Row = List[str]
Table = Tuple[List[Row], List[Row]]  # (header rows, body rows)

MIN_COLUMN_WIDTH = 3  # GFM requires at least three dashes in the separator row


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: List[Table] = []
        self._table_depth = 0
        self._in_thead = False
        self._row: Optional[Row] = None
        self._cell: Optional[List[str]] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            if self._table_depth == 0:
                self.tables.append(([], []))
            self._table_depth += 1
        elif self._table_depth == 0:
            return
        elif tag == "thead":
            self._in_thead = True
        elif tag == "tr":
            self._row = []
        elif tag in ("th", "td"):
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self._table_depth == 0:
            return
        if tag == "table":
            self._table_depth -= 1
        elif tag == "thead":
            self._in_thead = False
        elif tag in ("th", "td") and self._cell is not None and self._row is not None:
            text = " ".join("".join(self._cell).split()).replace("|", "\\|")
            self._row.append(text)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            header_rows, body_rows = self.tables[-1]
            (header_rows if self._in_thead else body_rows).append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _render_table(header_rows: List[Row], body_rows: List[Row]) -> Optional[str]:
    if header_rows:
        header, body = header_rows[0], header_rows[1:] + body_rows
    elif body_rows:
        header, body = body_rows[0], body_rows[1:]
    else:
        return None

    n_cols = max(len(row) for row in [header, *body])
    rows = [row + [""] * (n_cols - len(row)) for row in [header, *body]]
    widths = [max(MIN_COLUMN_WIDTH, *(len(row[i]) for row in rows)) for i in range(n_cols)]

    def fmt(row: Row) -> str:
        return "| " + " | ".join(cell.ljust(w) for cell, w in zip(row, widths)) + " |"

    separator = "| " + " | ".join("-" * w for w in widths) + " |"
    return "\n".join([fmt(rows[0]), separator, *(fmt(row) for row in rows[1:])])


def html_tables_to_markdown(html: str) -> Optional[str]:
    """Render every <table> in ``html`` as a padded GFM pipe table.

    Tables are separated by a blank line. Returns None when no table has rows.
    """
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    rendered = [_render_table(*table) for table in parser.tables]
    rendered = [table for table in rendered if table is not None]
    if not rendered:
        return None
    return "\n\n".join(rendered)
