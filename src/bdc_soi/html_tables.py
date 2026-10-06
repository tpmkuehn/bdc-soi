"""HTML SOI table discovery and reconstruction (SPEC 12).

Pipeline per table: cell grid -> header-row detection -> colspan expansion -> column
compression (spacers, split currency symbols, trailing ')'/'%' cells) -> header
flattening -> column mapping -> scale detection -> row classification -> carry-forward.
Every scored table is recorded, including rejected ones with reasons.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from lxml import etree, html as lxml_html

from bdc_soi.normalization import ParsedNumber, collapse_ws, parse_number, strip_footnote_markers, text_key
from bdc_soi.templates import HtmlSpec, RowRules

GENERIC_HEADER_ALIASES: dict[str, list[str]] = {
    "issuer": [r"^Portfolio\s+Company", r"^Issuer", r"^Company", r"^Investments?$", r"^Name\s+of\s+(?:Portfolio\s+)?Company", r"^Borrower", r"^Portfolio\s+Investments?$", r"Industry\s*/\s*Company", r"Company\s*/\s*Industry", r"\bPortfolio\s+Company\b", r"\bIssuer\b", r"\bBorrower\b", r"\bCompany\s+Name\b"],
    "description": [r"^Investment\s+Type", r"^Description", r"^Type\s+of\s+Investment", r"^Security", r"^Instrument", r"^Investment$", r"^Title\s+of\s+Securities"],
    "industry": [r"^Industry", r"^Sector", r"^Business\s+Description"],
    "interest_rate_text": [r"Reference\s+Rate\s+and\s+Spread", r"Spread\s+Above\s+Index", r"Index\s*\+?\s*Spread", r"^Rate\s+Type", r"Spread\s+Above\s+Reference"],
    "interest_rate": [r"^Interest\s+Rate", r"^Coupon", r"^Total\s+Coupon", r"^All[\s-]*in\s+Rate", r"^Cash\s+Interest", r"^Rate$", r"^Interest$"],
    "rate_floor": [r"^Floor", r"Index\s+Floor", r"Interest\s+Rate\s+Floor"],
    "reference_index": [r"^Index\b", r"^Reference\s+Rate$", r"^Base\s+Rate$", r"^Benchmark"],
    "spread": [r"^Spread\b"],
    "maturity_date": [r"^Maturity", r"Maturity\s+Date", r"^Expiration"],
    "issue_date": [r"^Issue\s+Date", r"^Issuance\s+Date"],
    "principal_amount": [r"^Principal", r"Par\s+(?:Value|Amount)", r"Principal\s+Amount", r"^Par$", r"Principal/\s*Par", r"Par\s*/\s*Shares", r"Principal\s*/\s*Shares", r"^Units?$"],
    "shares": [r"^Shares", r"Number\s+of\s+Shares", r"^Units", r"Shares\s*/\s*Units", r"^Quantity"],
    "amortized_cost": [r"Amortized\s+Cost"],
    "cost": [r"^(?!.*Amortized)(?:Cost|Cost\s+Basis)$", r"^Cost\b(?!.*Amortized)", r"^Original\s+Cost"],
    "fair_value": [r"Fair\s+Value", r"^Value$", r"Market\s+Value"],
    "percent_of_net_assets": [r"%\s*of\s+Net\s+Assets", r"Percentage\s+of\s+Net\s+Assets", r"Percent\s+of\s+Net\s+Assets", r"%\s+of\s+NAV"],
    "footnote_markers": [r"^Footnotes?$", r"^Notes?$"],
    "country": [r"^Country", r"^Geograph", r"^Location", r"^Headquarters"],
    "currency": [r"^Currency"],
}
COMBINED_PAR_SHARES_RE = re.compile(r"(Par|Principal).*(Shares|Units)|(Shares|Units).*(Par|Principal)", re.IGNORECASE)
EQUITY_LIKE_RE = re.compile(r"\b(Equity|Stock|Shares?|Units?|Warrants?|Preferred|Common|Membership|Partnership|Interests?|LP\b|Class\s+[A-Z]|Options?)\b", re.IGNORECASE)
GENERIC_GROUP_HEADING_RULES: list[tuple[str, str]] = [
    (r"affiliat|control", "affiliate_status"),
    (r"^(?:First|Second|Third)[\s-]+Lien|^Senior\s+Secured|^Subordinated|^Unsecured|^Equity|^Preferred|^Common|^Warrants?|^Debt\s+Investments|^Structured|^Joint\s+Venture|^Mezzanine|^Unitranche", "investment_type"),
]
GENERIC_TOTAL_REGEX = [r"^Total\s+(?:Portfolio\s+)?Investments\b(?!\s+in\s)(?!\s+(?:and|&)\s+Cash)", r"^Total\s+Investments\s+(?:at|in)\s+Fair\s+Value", r"^Investments\s+at\s+Fair\s+Value"]
NON_HOLDING_ROW_REGEX = [r"^Liabilities\s+in\s+Excess\s+of\s+Other\s+Assets", r"^Other\s+Assets\s+in\s+Excess", r"^Net\s+Assets\b", r"^Total\s+Net\s+Assets", r"^Other\s+Assets", r"^Total\s+Liabilities"]
GENERIC_SUBTOTAL_REGEX = [r"^(?:Sub)?[Tt]otal\b"]
GENERIC_FOOTNOTE_REGEX = [r"^\(?\d{1,2}\)?\s", r"^\([a-z]\)\s", r"^\*\s", r"^See\s+accompanying\s+notes", r"^The\s+accompanying\s+notes"]
GENERIC_HEADING_REGEX = [r"Schedule\s+of\s+Investments", r"Consolidated\s+Schedule\s+of\s+Investments", r"Investment\s+Portfolio"]
GENERIC_EXCLUDED_TERMS = [r"Fair\s+Value\s+Hierarchy", r"Percentage\s+of\s+Total\s+Investments", r"%\s*of\s+Total\s+Investments", r"Gross\s+Additions", r"Gross\s+Reductions", r"Non-?Accrual\s+Status", r"Beginning\s+Fair\s+Value", r"Change\s+in\s+Unrealized", r"Dividend\s+and\s+Interest\s+Income", r"Realized\s+Gain", r"Investment\s+Activity", r"Unfunded\s+Commitment", r"Commitment\s+Expiration", r"Risk\s+Rating", r"Investment\s+Rating", r"Performance\s+Rating", r"Internal\s+Rating", r"\bGrade\s+[1-5]\b", r"Financial\s+Highlights", r"Level\s+[123]\b", r"Significant\s+Unobservable", r"Valuation\s+Technique", r"Statements?\s+of\s+Assets\s+and\s+Liabilities", r"Statements?\s+of\s+Operations", r"Statements?\s+of\s+Cash\s+Flows", r"Changes\s+in\s+Net\s+Assets"]
THOUSANDS_RE = [r"amounts?\s+in\s+thousands", r"\$\s*in\s+thousands", r"\(in\s+thousands", r"dollars?\s+in\s+thousands", r"in\s+thousands\b", r"\(000s?\)", r"000s\s+omitted"]
MILLIONS_RE = [r"amounts?\s+in\s+millions", r"\$\s*in\s+millions", r"\(in\s+millions", r"dollars?\s+in\s+millions", r"in\s+millions\b"]
_DATE_TEXT_RE = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(\d{4})", re.IGNORECASE)
NUMERIC_HOLDING_FIELDS = ("fair_value", "cost", "amortized_cost", "principal_amount", "shares", "face_amount")
_MONETARY_FIELDS = {"fair_value", "cost", "amortized_cost", "principal_amount", "face_amount"}
_BLOCK_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table"}
CURRENCY_SYMBOLS = [("C$", "CAD"), ("A$", "AUD"), ("NZ$", "NZD"), ("S$", "SGD"), ("HK$", "HKD"), ("US$", "USD"), ("$", "USD"), ("£", "GBP"), ("€", "EUR"), ("¥", "JPY"), ("CHF", "CHF"), ("CAD", "CAD"), ("AUD", "AUD"), ("EUR", "EUR"), ("GBP", "GBP"), ("USD", "USD"), ("NOK", "NOK"), ("SEK", "SEK"), ("DKK", "DKK"), ("kr", None)]
_CURRENCY_RE = re.compile(r"(?:(?<![A-Za-z])(C\$|A\$|NZ\$|S\$|HK\$|US\$|CAD|AUD|EUR|GBP|USD|CHF|NOK|SEK|DKK)(?![A-Za-z])|[$£€¥])")


_CURRENCY_ONLY_RE = re.compile(r"(?:C\$|A\$|NZ\$|S\$|HK\$|US\$|CAD|AUD|EUR|GBP|USD|CHF|NOK|SEK|DKK|[$£€¥])")


def disclosed_currency(text: str) -> tuple[str | None, str | None]:
    """Return (ISO code, symbol text) when the cell text itself carries a currency symbol or code."""
    m = _CURRENCY_RE.search(text or "")
    if not m:
        return None, None
    sym = m.group(0)
    for s, code in CURRENCY_SYMBOLS:
        if sym == s:
            return code, sym
    return None, sym


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Cell:
    text: str
    colspan: int = 1
    rowspan: int = 1


@dataclass
class HtmlRow:
    table_index: int
    row_index: int
    row_id: str
    classification: str
    cells: list[str]
    row_text: str
    fields_raw: dict[str, str] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)
    carried: dict[str, str] = field(default_factory=dict)  # field -> source row_id
    group_context: dict[str, str] = field(default_factory=dict)
    numeric_kinds: dict[str, str] = field(default_factory=dict)
    footnotes: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    currency_symbols: dict[str, dict[str, str]] = field(default_factory=dict)  # field -> {code, symbol, source_row_id}

    def to_row(self) -> dict[str, Any]:
        return {
            "table_index": self.table_index,
            "currency_symbols": json.dumps(self.currency_symbols, sort_keys=True),
            "row_index": self.row_index,
            "row_id": self.row_id,
            "classification": self.classification,
            "row_text": self.row_text[:500],
            "fields_raw": json.dumps(self.fields_raw, sort_keys=True),
            "fields": json.dumps({k: (v.isoformat() if isinstance(v, date) else v) for k, v in self.fields.items()}, sort_keys=True),
            "carried": json.dumps(self.carried, sort_keys=True),
            "group_context": json.dumps(self.group_context, sort_keys=True),
            "notes": json.dumps(self.notes),
        }


@dataclass
class TableResult:
    table_index: int
    table_id: str
    score: float
    accepted: bool
    reasons: list[str]
    heading_text: str
    heading_distance: int | None
    detected_dates: list[str]
    period_status: str  # current | comparative | undated | mixed
    header_rows: int
    flattened_headers: list[str]
    column_mapping: dict[int, str]
    column_mapping_rules: dict[int, str]
    scale_multiplier: int
    scale_source: str
    row_count: int
    holding_rows: int
    total_rows: int
    rows: list[HtmlRow] = field(default_factory=list)
    example_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        return {
            "table_index": self.table_index,
            "table_id": self.table_id,
            "score": self.score,
            "accepted": self.accepted,
            "reasons": json.dumps(self.reasons),
            "heading_text": self.heading_text[:300],
            "heading_distance": self.heading_distance,
            "detected_dates": json.dumps(self.detected_dates),
            "period_status": self.period_status,
            "header_rows": self.header_rows,
            "flattened_headers": json.dumps(self.flattened_headers),
            "column_mapping": json.dumps({str(k): v for k, v in sorted(self.column_mapping.items())}),
            "column_mapping_rules": json.dumps({str(k): v for k, v in sorted(self.column_mapping_rules.items())}),
            "scale_multiplier": self.scale_multiplier,
            "scale_source": self.scale_source,
            "row_count": self.row_count,
            "holding_rows": self.holding_rows,
            "total_rows": self.total_rows,
        }


@dataclass
class HtmlTotalCandidate:
    field: str
    value: float
    raw: str
    row_id: str
    row_text: str
    source: str  # html_template_total | html_generic_total | html_subtotal
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class HtmlExtraction:
    tables: list[TableResult]
    holding_rows: list[HtmlRow]
    totals: list[HtmlTotalCandidate]
    document_scale: int
    document_scale_source: str
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def element_text(el: etree._Element) -> str:
    parts: list[str] = []
    for node in el.iter():
        tag = node.tag if isinstance(node.tag, str) else ""
        local = tag.split("}")[-1].lower() if tag else ""
        if local in _BLOCK_TAGS:
            parts.append(" ")
        if node.text and local not in {"script", "style"}:
            parts.append(node.text)
        if node.tail and node is not el:
            parts.append(node.tail)
    return collapse_ws("".join(parts))


def _is_numeric_text(text: str) -> bool:
    p = parse_number(text)
    return p.value is not None


def detect_dates(text: str) -> list[str]:
    out: list[str] = []
    for m in _DATE_TEXT_RE.finditer(text):
        try:
            d = datetime.strptime(f"{m.group(1).title()} {m.group(2)}, {m.group(3)}", "%B %d, %Y").date()
        except ValueError:
            continue
        iso = d.isoformat()
        if iso not in out:
            out.append(iso)
    return out


def detect_scale(text: str, thousands: list[str] | None = None, millions: list[str] | None = None) -> int | None:
    for pat in (millions or []) + MILLIONS_RE:
        if re.search(pat, text, re.IGNORECASE):
            return 1_000_000
    for pat in (thousands or []) + THOUSANDS_RE:
        if re.search(pat, text, re.IGNORECASE):
            return 1000
    return None


# ---------------------------------------------------------------------------
# Grid construction
# ---------------------------------------------------------------------------


def table_cells(table: etree._Element) -> list[list[Cell]]:
    rows: list[list[Cell]] = []
    for tr in table.iter():
        if not isinstance(tr.tag, str) or tr.tag.split("}")[-1].lower() != "tr":
            continue
        # Skip rows of nested tables.
        parent_table = tr
        while parent_table is not None and (not isinstance(parent_table.tag, str) or parent_table.tag.split("}")[-1].lower() != "table"):
            parent_table = parent_table.getparent()
        if parent_table is not table:
            continue
        cells: list[Cell] = []
        for td in tr:
            if not isinstance(td.tag, str) or td.tag.split("}")[-1].lower() not in {"td", "th"}:
                continue
            try:
                cs = max(1, int(td.get("colspan", "1") or 1))
            except ValueError:
                cs = 1
            try:
                rs = max(1, int(td.get("rowspan", "1") or 1))
            except ValueError:
                rs = 1
            cells.append(Cell(element_text(td), cs, rs))
        rows.append(cells)
    return rows


def _alias_patterns(spec: HtmlSpec | None) -> list[tuple[str, re.Pattern[str], str]]:
    pats: list[tuple[str, re.Pattern[str], str]] = []
    if spec:
        for fld, lst in spec.header_aliases.items():
            for p in lst:
                pats.append((fld, re.compile(p, re.IGNORECASE), f"template_header_alias:{p}"))
    for fld, lst in GENERIC_HEADER_ALIASES.items():
        for p in lst:
            pats.append((fld, re.compile(p, re.IGNORECASE), f"generic_header_alias:{p}"))
    return pats


def _looks_like_header_row(cells: list[Cell], alias_pats: list[tuple[str, re.Pattern[str], str]]) -> bool:
    texts = [c.text for c in cells if c.text]
    if not texts:
        return False
    numeric = sum(1 for t in texts if _is_numeric_text(t) and not re.search(r"[A-Za-z]{3,}", t))
    if numeric > 0 and numeric >= len(texts) / 2:
        return False
    hits = sum(1 for t in texts for _f, pat, _r in alias_pats if pat.search(strip_footnote_markers(t)[0]))
    return hits > 0


def is_title_row(cells: list[Cell], width: int) -> bool:
    """A single text cell spanning (almost) the whole table is a caption/title, not a header row."""
    texts = [c for c in cells if c.text]
    return len(texts) == 1 and texts[0].colspan >= max(2, int(width * 0.8)) and not _is_numeric_text(texts[0].text)


def detect_header_rows(rows: list[list[Cell]], spec: HtmlSpec | None, alias_pats: list[tuple[str, re.Pattern[str], str]]) -> int:
    max_rows = spec.header_rows.max if spec else 4
    width = max((sum(c.colspan for c in r) for r in rows), default=0)
    count = 0
    header_rows_seen = 0
    for i, cells in enumerate(rows[: max_rows + 4]):
        texts = [c.text for c in cells if c.text]
        if not texts:
            if count == 0:
                continue  # leading blank rows before the header
            break
        if count == 0 and is_title_row(cells, width):
            continue  # caption row above the header
        if _looks_like_header_row(cells, alias_pats):
            count = i + 1
            header_rows_seen += 1
        elif count:
            break
        if header_rows_seen >= max_rows:
            break
    return count


def expand_grid(rows: list[list[Cell]], header_rows: int) -> list[list[str]]:
    """Expand colspans: header text is replicated across spanned columns; body text fills the first."""
    width = max((sum(c.colspan for c in r) for r in rows), default=0)
    grid: list[list[str]] = []
    pending_rowspans: dict[int, tuple[str, int]] = {}
    for ri, cells in enumerate(rows):
        out = [""] * width
        col = 0
        is_header = ri < header_rows
        if is_title_row(cells, width):
            grid.append(out)  # caption rows carry no column semantics
            continue
        # Apply rowspans from previous rows.
        for c_idx, (text, remaining) in list(pending_rowspans.items()):
            if remaining > 0:
                out[c_idx] = text if is_header else ""
                pending_rowspans[c_idx] = (text, remaining - 1)
            if pending_rowspans[c_idx][1] <= 0:
                del pending_rowspans[c_idx]
        for cell in cells:
            while col < width and col in pending_rowspans:
                col += 1
            if col >= width:
                break
            for k in range(cell.colspan):
                if col + k >= width:
                    break
                out[col + k] = cell.text if (is_header or k == 0) else ""
            if cell.rowspan > 1:
                pending_rowspans[col] = (cell.text, cell.rowspan - 1)
            col += cell.colspan
        grid.append(out)
    return grid


def compress_columns(grid: list[list[str]], header_rows: int, layout: dict[str, Any] | None = None) -> tuple[list[list[str]], list[str]]:
    """Drop spacer columns and merge split currency-symbol / trailing ')' '%' columns.

    When ``layout`` (a previous page's ``keep``/``merge_right``/``merge_left`` column sets) is given, that layout is
    applied verbatim so a header-less continuation page lines up with the page that carried the header.
    """
    if not grid:
        return grid, []
    if layout is not None:
        keep, merge_right, merge_left = list(layout["keep"]), set(layout["merge_right"]), set(layout["merge_left"])
        width = len(grid[0])
        out: list[list[str]] = []
        for ri, row in enumerate(grid):
            new_row: list[str] = []
            for ci in keep:
                text = row[ci] if ci < width else ""
                nxt = ci + 1
                while nxt < width and nxt in merge_left:
                    if row[nxt].strip():
                        text = (text + row[nxt].strip()) if text else text
                    nxt += 1
                prev = ci - 1
                while prev >= 0 and prev in merge_right:
                    if row[prev].strip() and text and not text.startswith("$"):
                        text = row[prev].strip() + text
                    prev -= 1
                new_row.append(text)
            out.append(new_row)
        return out, ["applied_previous_page_layout"]
    width = len(grid[0])
    body = grid[header_rows:] if header_rows < len(grid) else []
    notes: list[str] = []

    def col_values(ci: int) -> list[str]:
        return [r[ci] for r in body if ci < len(r)]

    keep: list[int] = []
    merge_right: set[int] = set()
    merge_left: set[int] = set()
    for ci in range(width):
        vals = [v for v in col_values(ci) if v.strip()]
        if not vals:
            if any(r[ci].strip() for r in grid[:header_rows]):
                # Header text in an otherwise empty column: keep only if nothing else carries that header.
                continue
            continue
        if all(re.fullmatch(r"[\$€£¥]", v.strip()) for v in vals):
            merge_right.add(ci)
            continue
        if all(re.fullmatch(r"[\)%]+|\)\s*%|%\s*\)", v.strip()) for v in vals):
            merge_left.add(ci)
            continue
        keep.append(ci)
    if merge_right:
        notes.append(f"merged_currency_columns:{sorted(merge_right)}")
    if merge_left:
        notes.append(f"merged_suffix_columns:{sorted(merge_left)}")
    _LAST_LAYOUT["keep"], _LAST_LAYOUT["merge_right"], _LAST_LAYOUT["merge_left"], _LAST_LAYOUT["raw_width"] = list(keep), sorted(merge_right), sorted(merge_left), width
    out: list[list[str]] = []
    for ri, row in enumerate(grid):
        new_row: list[str] = []
        for ci in keep:
            text = row[ci]
            # Pull trailing ')' or '%' from the next merge-left columns.
            nxt = ci + 1
            while nxt < width and nxt in merge_left:
                if ri >= header_rows and row[nxt].strip():
                    text = (text + row[nxt].strip()) if text else text
                nxt += 1
            prev = ci - 1
            while prev >= 0 and prev in merge_right:
                if ri >= header_rows and row[prev].strip() and text and not text.startswith("$"):
                    text = row[prev].strip() + text
                prev -= 1
            new_row.append(text)
        out.append(new_row)
    return out, notes


_LAST_LAYOUT: dict[str, Any] = {}  # layout applied by the most recent compress_columns call (read immediately after)


def flatten_headers(grid: list[list[str]], header_rows: int) -> list[str]:
    if not grid:
        return []
    width = len(grid[0])
    headers: list[str] = []
    for ci in range(width):
        parts: list[str] = []
        for ri in range(min(header_rows, len(grid))):
            t = collapse_ws(grid[ri][ci])
            if t and (not parts or parts[-1] != t):
                parts.append(t)
        joined = collapse_ws(" ".join(parts))
        joined = re.sub(r"^(Unnamed(?::\s*\d+)?\s*)+", "", joined, flags=re.IGNORECASE)
        headers.append(joined)
    return headers


def merge_repeated_header_columns(grid: list[list[str]], headers: list[str], header_rows: int) -> tuple[list[list[str]], list[str], bool]:
    """Adjacent columns under one repeated header (e.g. 'Spread Above Index' split into 'SF +' and '5.50%') are one column."""
    if not headers:
        return grid, headers, False
    groups: list[list[int]] = []
    for ci, h in enumerate(headers):
        if groups and h and headers[groups[-1][0]] == h:
            groups[-1].append(ci)
        else:
            groups.append([ci])
    if all(len(g) == 1 for g in groups):
        return grid, headers, False
    new_grid: list[list[str]] = []
    for ri, row in enumerate(grid):
        out: list[str] = []
        for g in groups:
            if ri < header_rows:
                out.append(row[g[0]])
            else:
                out.append(collapse_ws(" ".join(row[ci] for ci in g if ci < len(row) and row[ci].strip())))
        new_grid.append(out)
    return new_grid, [headers[g[0]] for g in groups], True


def map_columns(headers: list[str], alias_pats: list[tuple[str, re.Pattern[str], str]]) -> tuple[dict[int, str], dict[int, str], list[str]]:
    mapping: dict[int, str] = {}
    rules: dict[int, str] = {}
    notes: list[str] = []
    used: set[str] = set()
    for ci, header in enumerate(headers):
        h = strip_footnote_markers(header)[0]
        if not h:
            continue
        if COMBINED_PAR_SHARES_RE.search(h) and "principal_or_shares" not in used:
            mapping[ci] = "principal_or_shares"
            rules[ci] = "combined_par_shares_header"
            used.add("principal_or_shares")
            used.add("principal_amount")
            used.add("shares")
            continue
        for fld, pat, rule in alias_pats:
            if pat.search(h):
                if fld in used:
                    notes.append(f"duplicate_column_mapping:{fld}:col{ci}")
                    break
                mapping[ci] = fld
                rules[ci] = rule
                used.add(fld)
                break
    # Positional fallback: only a leading unmapped column can be the issuer (never a trailing one).
    if "issuer" not in used and headers:
        for ci in range(min(2, len(headers))):
            if ci not in mapping:
                mapping[ci] = "issuer"
                rules[ci] = "positional_leading_unmapped_column"
                notes.append(f"positional_issuer_column:{ci}")
                break
    return mapping, rules, notes


_FOOTNOTE_CELL_RE = re.compile(r"^(?:\(\s*[a-z0-9]{1,3}\s*\)\s*)+$", re.IGNORECASE)


def map_footnote_columns(grid: list[list[str]], header_rows: int, mapping: dict[int, str], rules: dict[int, str]) -> None:
    """An unmapped column whose body values are all footnote markers carries footnote_markers."""
    if not grid:
        return
    width = len(grid[0])
    for ci in range(width):
        if ci in mapping:
            continue
        vals = [r[ci].strip() for r in grid[header_rows:] if ci < len(r) and r[ci].strip()]
        if vals and all(_FOOTNOTE_CELL_RE.match(v) for v in vals) and "footnote_markers" not in mapping.values():
            mapping[ci] = "footnote_markers"
            rules[ci] = "footnote_marker_column_heuristic"


# ---------------------------------------------------------------------------
# Heading context
# ---------------------------------------------------------------------------


def _contains_table(el: etree._Element) -> bool:
    return any(isinstance(n.tag, str) and n.tag.split("}")[-1].lower() == "table" for n in el.iter())


def _text_after_last_table(el: etree._Element) -> str:
    """Text of ``el`` that follows its last nested table (recursing into the child holding that table)."""
    children = [c for c in el if isinstance(c.tag, str)]
    idx = next((i for i in range(len(children) - 1, -1, -1) if _contains_table(children[i])), None)
    if idx is None:
        return element_text(el)
    last = children[idx]
    parts = [] if last.tag.split("}")[-1].lower() == "table" else [_text_after_last_table(last)]
    parts.append(last.tail or "")
    for c in children[idx + 1 :]:
        parts.append(element_text(c))
        parts.append(c.tail or "")
    return collapse_ws(" ".join(parts))


def preceding_text(table: etree._Element, max_distance: int) -> tuple[str, int | None, str]:
    """Collect text from up to ``max_distance`` preceding block elements; returns (text, distance_to_heading, nearest_block)."""
    texts: list[str] = []
    node: etree._Element | None = table
    steps = 0
    while node is not None and steps < max_distance:
        prev = node.getprevious()
        while prev is None and node is not None:
            node = node.getparent()
            if node is None or (isinstance(node.tag, str) and node.tag.split("}")[-1].lower() == "body"):
                node = None
                break
            prev = node.getprevious()
        if prev is None:
            break
        node = prev
        if not isinstance(prev.tag, str):
            continue
        if prev.tag.split("}")[-1].lower() == "table":
            steps += 1
            continue
        if _contains_table(prev):
            # A block wrapping a table (page container) is the previous page: only text after its last nested
            # table can describe this table; the statement text inside must not leak into this heading.
            steps += 1
            t = _text_after_last_table(prev)
            if t:
                texts.append(t)
            continue
        t = element_text(prev)
        if t:
            texts.append(t)
            steps += 1
    joined = " \n ".join(reversed(texts))
    # Nearest blocks (closest first) drive period and scale detection; the closest block carrying a
    # date decides the period so that a preceding unrelated table's text cannot leak another date in.
    dated = next((t for t in texts[:6] if _DATE_TEXT_RE.search(t)), None)
    nearest_blocks = " \n ".join(reversed(texts[:3]))
    if dated is not None and dated not in texts[:3]:
        nearest_blocks = dated + " \n " + nearest_blocks
    return joined, (len(texts) if texts else None), (dated or "") + " \n " + nearest_blocks + " \n\x1e" + (texts[0] if texts else "")


# ---------------------------------------------------------------------------
# Row classification (12.5)
# ---------------------------------------------------------------------------


def _compile_list(pats: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in pats]


def _holding_like_fields(fields_raw: dict[str, str], first_text: str) -> bool:
    """True when the row carries facility evidence beyond its label: a parsable date, a rate-looking cell or a
    description that is not just the row label spilling across columns (Apollo subtotal labels span columns)."""
    fk = text_key(first_text)
    for f in ("description", "reference_index"):
        v = fields_raw.get(f)
        if v and text_key(v) != fk and text_key(v) not in fk:
            return True
    for f in ("interest_rate", "interest_rate_text", "spread"):
        v = fields_raw.get(f)
        if v and text_key(v) != fk and re.search(r"\d|%|\+", v):
            return True
    v = fields_raw.get("maturity_date")
    if v and _DATE_LIKE_RE.search(v):
        return True
    return False


_DATE_LIKE_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}")


def classify_row(
    cells: list[str],
    mapping: dict[int, str],
    headers: list[str],
    rules: RowRules | None,
    compiled: dict[str, list[re.Pattern[str]]],
) -> tuple[str, dict[str, str], str]:
    texts = [c for c in cells if c.strip()]
    if not texts:
        return "blank", {}, ""
    row_text = collapse_ws(" ".join(texts))
    first_text = strip_footnote_markers(texts[0])[0]
    fields_raw: dict[str, str] = {ci_field: cells[ci] for ci, ci_field in mapping.items() if ci < len(cells) and cells[ci].strip()}
    # Repeated header rows.
    if headers and sum(1 for ci, h in enumerate(headers) if h and ci < len(cells) and text_key(cells[ci]) == text_key(h)) >= max(2, len([h for h in headers if h]) // 2):
        return "repeated_header", fields_raw, row_text
    numeric_fields = {f: v for f, v in fields_raw.items() if (f in NUMERIC_HOLDING_FIELDS or f == "principal_or_shares") and _is_numeric_text(v)}
    for pat in compiled["total"]:
        if pat.search(first_text) or pat.search(row_text):
            return "total", fields_raw, row_text
    holding_like = _holding_like_fields(fields_raw, first_text)
    for pat in compiled["subtotal"]:
        if pat.search(first_text) and not holding_like:
            return "subtotal", fields_raw, row_text  # an issuer named 'Total Fleet Buyer, LLC' with a facility/rate/maturity is a holding
    for pat in compiled["skip"]:
        if pat.search(first_text):
            return "skipped", fields_raw, row_text
    for pat in compiled["footnote"]:
        if pat.search(first_text) and not numeric_fields:
            return "footnote", fields_raw, row_text
    if numeric_fields:
        descriptive_cells = [t for t in texts if not _is_numeric_text(t) and not _FOOTNOTE_CELL_RE.match(t.strip()) and parse_number(t).kind != "null" and not _CURRENCY_ONLY_RE.fullmatch(t.strip())]
        if not descriptive_cells:
            return "subtotal", fields_raw, row_text  # numbers only: an issuer/group subtotal line, not a holding
        return "holding", fields_raw, row_text
    content = [t for t in texts if not _FOOTNOTE_CELL_RE.match(t.strip())]  # footnote cells are not content
    if len(content) == 1 and not _is_numeric_text(content[0]):
        return "group_heading", fields_raw, row_text
    descriptive = [f for f in fields_raw if f in {"issuer", "description", "industry"}]
    if descriptive and len(content) <= 2:
        return "group_heading", fields_raw, row_text
    return "unknown", fields_raw, row_text


def _apply_scale(fld: str, parsed: ParsedNumber, multiplier: int) -> Any:
    if parsed.value is None:
        return None
    if fld in _MONETARY_FIELDS:
        return parsed.value * multiplier
    if fld == "percent_of_net_assets":
        return parsed.value / 100.0 if parsed.kind in {"percent", "number"} else parsed.value
    if fld in {"interest_rate", "rate_floor"}:
        if parsed.kind == "percent" or parsed.kind == "number":
            return parsed.value / 100.0
        if parsed.kind == "bps":
            return parsed.value / 10000.0
    return parsed.value


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------


_HEADING_NOISE_RE = re.compile(r"\s*\((?:continued|cont\.?|concluded)\)\s*", re.IGNORECASE)


def clean_heading_value(text: str) -> str:
    """Strip footnote markers, '(Continued)' page-break noise and trailing colons from a heading value."""
    t = _HEADING_NOISE_RE.sub(" ", text)
    t = re.sub(r"\s*\([a-z0-9]{1,3}\)(?=\s*(?:\([a-z0-9]{1,3}\)\s*)*:?\s*$)", "", t, flags=re.IGNORECASE)
    t = strip_footnote_markers(t)[0]
    t = re.sub(r"\s*[-–—]\s*\(?-?\d+(?:\.\d+)?\s*%\)?\s*$", "", t)  # 'Multifamily - 158.9%' -> 'Multifamily'
    t = re.sub(r"\s*\(\s*-?\d+(?:\.\d+)?\s*%\s*\)\s*$", "", t)
    return collapse_ws(t).rstrip(":").strip()


def _heading_target_for(text: str, rules: RowRules | None, default_target: str | None) -> str | None:
    for ghr in (rules.group_heading_rules if rules else []):
        if re.search(ghr.regex, text, re.IGNORECASE):
            return ghr.target
    for pat, target in GENERIC_GROUP_HEADING_RULES:
        if re.search(pat, text, re.IGNORECASE):
            return target
    return default_target


def extract_html(
    path: Path,
    report_date: date | None,
    spec: HtmlSpec | None,
    *,
    max_example_rows: int = 5,
    known_group_values: dict[str, set[str]] | None = None,
    template_is_company: bool = False,
) -> HtmlExtraction:
    """Extract SOI tables. ``known_group_values`` maps a field (industry, investment_type, affiliate_status)
    to values disclosed elsewhere in the filing (e.g. XBRL classification members); a group-heading row that
    equals a known value is assigned to that field instead of the template default target."""
    known_keys: dict[str, str] = {}
    for fld, values in (known_group_values or {}).items():
        for v in values:
            k = text_key(re.sub(r"\s*\[Member\]\s*$", "", v))
            if k:
                known_keys.setdefault(k, fld)
    data = Path(path).read_bytes()
    parser = lxml_html.HTMLParser(huge_tree=True, encoding="utf-8")
    try:
        doc = lxml_html.fromstring(data, parser=parser)
    except (etree.ParserError, ValueError):
        doc = lxml_html.fromstring(data.decode("utf-8", errors="ignore"))
    for bad in doc.iter():
        if isinstance(bad.tag, str) and bad.tag.split("}")[-1].lower() in {"script", "style"}:
            bad.text = ""
    body_text = element_text(doc)
    td = spec.table_detection if spec else None
    heading_pats = _compile_list((td.heading_regex if td else []) + GENERIC_HEADING_REGEX)
    required_pats = _compile_list(td.required_terms if td and td.required_terms else [r"Fair\s+Value"])
    optional_pats = _compile_list(td.optional_terms if td and td.optional_terms else [r"Cost", r"Principal|Par", r"Maturity"])
    excluded_pats = _compile_list((td.excluded_terms if td else []) + GENERIC_EXCLUDED_TERMS)
    minimum_score = td.minimum_score if td else 6
    max_heading_distance = td.max_heading_distance if td else 20
    alias_pats = _alias_patterns(spec)
    rules = spec.row_rules if spec else None
    compiled = {
        "total": _compile_list((rules.total_if_regex if rules else []) or GENERIC_TOTAL_REGEX),
        "subtotal": _compile_list((rules.subtotal_if_regex if rules else []) or GENERIC_SUBTOTAL_REGEX),
        "skip": _compile_list((rules.skip_if_regex if rules else []) + NON_HOLDING_ROW_REGEX),
        "footnote": _compile_list((rules.footnote_if_regex if rules else []) or GENERIC_FOOTNOTE_REGEX),
    }
    sc = spec.scale if spec else None
    doc_scale = None
    doc_scale_source = "default"
    if sc and sc.source == "fixed" and sc.fixed_multiplier:
        doc_scale, doc_scale_source = sc.fixed_multiplier, "template_fixed"
    else:
        # Document-level: look near SOI headings first, then anywhere.
        for m in heading_pats[0].finditer(body_text) if heading_pats else []:
            window = body_text[m.start() : m.start() + 600]
            val = detect_scale(window, sc.thousands_regex if sc else None, sc.millions_regex if sc else None)
            if val:
                doc_scale, doc_scale_source = val, "document_soi_heading_window"
                break
        if doc_scale is None:
            val = detect_scale(body_text[:20000], sc.thousands_regex if sc else None, sc.millions_regex if sc else None)
            if val:
                doc_scale, doc_scale_source = val, "document_front_matter"
    default_scale = sc.default if sc else 1

    tables = [t for t in doc.iter() if isinstance(t.tag, str) and t.tag.split("}")[-1].lower() == "table"]
    results: list[TableResult] = []
    holding_rows: list[HtmlRow] = []
    totals: list[HtmlTotalCandidate] = []
    carry_state: dict[str, str] = {}
    carry_source: dict[str, str] = {}
    group_context: dict[str, str] = {}
    prev_accepted = False
    after_total = False  # set once a grand-total row has been seen in the accepted SOI sequence
    prev_layout: dict[str, Any] | None = None  # column mapping of the last accepted table, for header-less continuation pages
    column_currency: dict[str, dict[str, str]] = {}  # field -> {code, symbol, source_row_id}: last symbol disclosed in that column
    state: dict[str, Any] = {"prev_accepted": prev_accepted, "after_total": after_total, "prev_layout": prev_layout, "carry_state": carry_state, "carry_source": carry_source, "group_context": group_context, "column_currency": column_currency}
    deferred: list[tuple[int, Any]] = []  # header-less schedule pages waiting for the next header page's layout

    def process(ti: int, table: Any, forced_layout: dict[str, Any] | None = None) -> None:
        prev_accepted = state["prev_accepted"]
        after_total = state["after_total"]
        prev_layout = forced_layout if forced_layout is not None else state["prev_layout"]
        carry_state, carry_source, group_context, column_currency = state["carry_state"], state["carry_source"], state["group_context"], state["column_currency"]
        raw_rows = table_cells(table)
        if len(raw_rows) < 2:
            return
        width0 = max((sum(c.colspan for c in r) for r in raw_rows), default=0)
        captions = " \n ".join(c.text for r in raw_rows[:6] if is_title_row(r, width0) for c in r if c.text)
        header_n = detect_header_rows(raw_rows, spec, alias_pats)
        grid = expand_grid(raw_rows, header_n)
        heading_text, heading_distance, nearest = preceding_text(table, max_heading_distance)
        nearest, _, closest_block = nearest.partition(" \n\x1e")
        inherited = False
        raw_width = len(grid[0]) if grid else 0
        schedule_page = header_n == 0 and (ti == (prev_layout["table_index"] + 1 if prev_layout else -99) or (re.search(r"continued", closest_block, re.IGNORECASE) is not None and any(p.search(closest_block) for p in heading_pats)))
        continuation = schedule_page and prev_layout is not None and raw_width == prev_layout["raw_width"]
        if forced_layout is None and schedule_page and not continuation and len(raw_rows) >= 3 and not state.get("draining"):
            deferred.append((ti, table))  # try the next header page's layout
            return
        if continuation:
            # Continuation page of the schedule without a repeated header row (SPEC 12.3/12.6): apply the previous
            # page's column layout and mapping verbatim; recorded as an inherited layout.
            grid, comp_notes = compress_columns(grid, 0, prev_layout["compression"])
            if prev_layout.get("merge_groups"):
                grid = [[collapse_ws(" ".join(row[ci] for ci in g if ci < len(row) and row[ci].strip())) for g in prev_layout["merge_groups"]] for row in grid]
            mapping, map_rules, headers = dict(prev_layout["mapping"]), {ci: "inherited_from_previous_table" for ci in prev_layout["mapping"]}, list(prev_layout["headers"])
            map_notes = []
            inherited = True
        else:
            grid, comp_notes = compress_columns(grid, header_n)
            compression = dict(_LAST_LAYOUT)
            headers = flatten_headers(grid, header_n) if header_n else []
            merge_groups = None
            if headers:
                before = list(headers)
                grid, headers, merged = merge_repeated_header_columns(grid, headers, header_n)
                if merged:
                    comp_notes = list(comp_notes) + ["merged_repeated_header_columns"]
                    groups: list[list[int]] = []
                    for ci, hname in enumerate(before):
                        if groups and hname and before[groups[-1][0]] == hname:
                            groups[-1].append(ci)
                        else:
                            groups.append([ci])
                    merge_groups = groups
            mapping, map_rules, map_notes = map_columns(headers, alias_pats) if headers else ({}, {}, [])
            if headers:
                map_footnote_columns(grid, header_n, mapping, map_rules)
            pos_ci = next((ci for ci, f in mapping.items() if f == "issuer" and map_rules.get(ci, "").startswith("positional")), None)
            if pos_ci is not None:
                vals = [row[pos_ci] for row in grid[header_n:] if pos_ci < len(row) and row[pos_ci].strip()]
                if vals and sum(1 for v in vals if _is_numeric_text(v)) * 2 >= len(vals):
                    # A positional issuer column holding numbers is a summary table's value column, not issuers.
                    mapping.pop(pos_ci)
                    map_rules.pop(pos_ci, None)
                    map_notes = list(map_notes) + [f"positional_issuer_column_numeric:col{pos_ci}"]
        if captions:
            nearest = captions + " \n " + nearest
            heading_text = heading_text + " \n " + captions
        header_text = " ".join(headers)
        reasons: list[str] = list(comp_notes) + list(map_notes)
        if inherited:
            reasons.append(f"inherited_header_from_{prev_layout['table_id']}")
        score = 0.0
        if any(p.search(heading_text) for p in heading_pats):
            score += 3
            reasons.append("heading_match")
        fields_present = set(mapping.values())
        if any(n.startswith("positional_issuer_column_numeric") for n in map_notes):
            score -= 5
        if "fair_value" in fields_present:
            score += 3
            reasons.append("fair_value_header")
        if {"cost", "amortized_cost"} & fields_present:
            score += 1
            reasons.append("cost_header")
        if {"principal_amount", "shares", "principal_or_shares"} & fields_present:
            score += 1
            reasons.append("principal_or_shares_header")
        if "maturity_date" in fields_present:
            score += 1
            reasons.append("maturity_header")
        if "issuer" in fields_present and map_rules.get(next((ci for ci, f in mapping.items() if f == "issuer"), -1), "").startswith(("template", "generic")):
            score += 1
            reasons.append("issuer_header")
        if "interest_rate_text" in fields_present or "interest_rate" in fields_present:
            score += 0.5
        issuer_col = next((ci for ci, f in mapping.items() if f == "issuer"), None)
        if not inherited and "description" not in fields_present and (issuer_col is None or map_rules.get(issuer_col, "").startswith("positional")):
            score -= 2
            reasons.append("no_descriptive_header")
        for p in required_pats:
            if not p.search(header_text) and not p.search(heading_text):
                score -= 3
                reasons.append(f"missing_required_term:{p.pattern}")
        for p in optional_pats:
            if p.search(header_text):
                score += 0.25
        excluded_hit = [p.pattern for p in excluded_pats if p.search(nearest) or p.search(header_text)]
        if excluded_hit:
            score -= 5
            reasons.append(f"excluded_terms:{excluded_hit}")
        if prev_accepted and not any(p.search(heading_text) for p in heading_pats) and "fair_value" in fields_present:
            score += 1
            reasons.append("continues_previous_soi_table")
        # Period detection.
        nearest_dated = nearest.split(" \n ")[0]
        dates = detect_dates(nearest_dated) or detect_dates(header_text)
        if report_date is None:
            period_status = "undated" if not dates else "current"
        elif not dates:
            period_status = "undated"
        elif report_date.isoformat() in dates and len(dates) == 1:
            period_status = "current"
        elif report_date.isoformat() in dates:
            period_status = "mixed"
        else:
            period_status = "comparative"
        accepted = score >= minimum_score and not excluded_hit
        if accepted and period_status == "comparative":
            accepted = False
            reasons.append("rejected:comparative_period_table")
        if accepted and period_status == "undated" and spec and not spec.period_selection.allow_undated_tables:
            accepted = False
            reasons.append("rejected:undated_table")
        if accepted and period_status == "undated" and header_n > 0 and after_total:
            # A new headed table after the schedule's grand-total row without a current-period date is another
            # schedule (observed: Onex comparative-period pages), not a continuation of the current one.
            accepted = False
            reasons.append("rejected:undated_headed_table_after_grand_total")
        if not accepted and score < minimum_score:
            reasons.append(f"rejected:score_below_minimum:{score}<{minimum_score}")
        # Scale (12.4 priority: template-fixed, table-local, nearest heading, document, default).
        table_local_text = " ".join(" ".join(r) for r in grid[: header_n + 1])
        if sc and sc.source == "fixed" and sc.fixed_multiplier:
            mult, mult_src = sc.fixed_multiplier, "template_fixed"
        else:
            local = detect_scale(table_local_text, sc.thousands_regex if sc else None, sc.millions_regex if sc else None)
            near = detect_scale(nearest + " " + heading_text[-300:], sc.thousands_regex if sc else None, sc.millions_regex if sc else None) if (sc is None or sc.source != "table_only") else None
            if local:
                mult, mult_src = local, "table_local_text"
            elif near:
                mult, mult_src = near, "nearest_heading"
            elif doc_scale and (sc is None or sc.source in {"table_then_document", "document_only"}):
                mult, mult_src = doc_scale, doc_scale_source
            else:
                mult, mult_src = default_scale, "default"
        rows_out: list[HtmlRow] = []
        holding_count = 0
        total_count = 0
        if accepted:
            if not (rules and rules.carry_forward_across_tables):
                carry_state, carry_source = {}, {}
                if not prev_accepted:
                    group_context = {}
                    after_total = False
                    column_currency = {}
            for ri in range(header_n, len(grid)):
                cells = grid[ri]
                cls, fields_raw, row_text = classify_row(cells, mapping, headers, rules, compiled)
                row = HtmlRow(ti, ri, f"t{ti}r{ri}", cls, cells, row_text, fields_raw)
                if cls == "group_heading":
                    heading_key = text_key(clean_heading_value(row_text))
                    default_target = (rules.group_heading_target if rules else "industry") or "industry"
                    target = known_keys.get(heading_key) or _heading_target_for(row_text, rules, default_target)
                    if target == "industry" and heading_key not in known_keys and "industry" in known_keys.values():
                        # The industry vocabulary is known (XBRL members) and this heading is not in it:
                        # treat it as a lower-level (issuer) heading rather than overwriting the industry.
                        target = "issuer"
                    if target == "ignore":
                        row.notes.append("heading_ignored_by_template_rule")
                    elif target:
                        group_context = dict(group_context)
                        name_cell = fields_raw.get("issuer") or fields_raw.get("description") if target == "issuer" else None
                        group_context[target] = clean_heading_value(name_cell or row_text)
                        if target != "issuer":
                            group_context.pop("issuer", None)  # an issuer heading belongs to the group it was under
                    carry_state, carry_source = {}, {}
                elif cls in {"total", "subtotal"}:
                    carry_state, carry_source = {}, {}
                    fields_raw.pop("principal_or_shares", None)
                    if cls == "total":
                        after_total = True
                    for fld, raw in fields_raw.items():
                        if fld in {"fair_value", "cost", "amortized_cost"}:
                            p = parse_number(raw)
                            if p.value is not None:
                                total_count += 1
                                # SPEC 16.1 ranks: 0 template XBRL total, 1 XBRL no-dimension, 2 company-template HTML total,
                                # 3 generic HTML total, 4 XBRL classification subtotal, 5 HTML subtotal.
                                if cls == "total" and template_is_company and rules and rules.total_if_regex:
                                    src, rank = "html_template_total", 2
                                elif cls == "total":
                                    src, rank = "html_generic_total", 3
                                else:
                                    src, rank = "html_subtotal", 5
                                totals.append(HtmlTotalCandidate(fld, p.value * mult, raw, row.row_id, row_text[:200], src, rank))
                            row.fields[fld] = p.value * mult if p.value is not None else None
                elif cls == "holding":
                    holding_count += 1
                    if after_total:
                        row.notes.append("after_total_row")
                    if "principal_or_shares" in fields_raw:
                        # Combined "Par/Shares" column: equity-like rows (no maturity/rate, equity description) carry a
                        # share count (unscaled); debt rows carry a scaled principal amount.
                        desc_text = fields_raw.get("description", "") or ""
                        has_debt_evidence = bool(_DATE_LIKE_RE.search(fields_raw.get("maturity_date") or "")) or bool(fields_raw.get("interest_rate")) or bool(fields_raw.get("interest_rate_text"))
                        raw_ps = fields_raw.pop("principal_or_shares")
                        if EQUITY_LIKE_RE.search(desc_text) and not has_debt_evidence:
                            fields_raw["shares"] = raw_ps
                            row.notes.append("combined_par_shares:shares")
                        else:
                            fields_raw["principal_amount"] = raw_ps
                            row.notes.append("combined_par_shares:principal")
                    for fld, raw in list(fields_raw.items()):
                        if fld in _MONETARY_FIELDS:
                            code, sym = disclosed_currency(raw)
                            if sym is not None:
                                column_currency[fld] = {"code": code or "", "symbol": sym, "source_row_id": row.row_id}
                            if fld in column_currency:
                                row.currency_symbols[fld] = dict(column_currency[fld])
                        if fld in NUMERIC_HOLDING_FIELDS or fld in {"percent_of_net_assets", "interest_rate", "rate_floor"}:
                            p = parse_number(raw)
                            if fld == "interest_rate" and p.kind == "text":
                                # Rate text such as "S+425, 0.50% Floor" is parsed by the rate parser, not dropped.
                                row.fields["interest_rate_text"] = collapse_ws(raw)
                                row.fields_raw["interest_rate_text"] = raw
                                continue
                            row.fields[fld] = _apply_scale(fld, p, mult)
                            row.numeric_kinds[fld] = p.kind
                            if p.footnotes:
                                row.footnotes[fld] = p.footnotes
                            if p.value is None and p.kind == "text":
                                row.notes.append(f"unparsed_numeric:{fld}:{raw[:40]}")
                        else:
                            txt, fn = strip_footnote_markers(collapse_ws(raw))
                            row.fields[fld] = txt
                            if fn:
                                row.footnotes[fld] = fn
                    # Carry-forward (12.6): template-controlled, reset at headings/totals/table boundaries.
                    cf = rules.carry_forward if rules else []
                    blanks_meaningful = set(rules.blanks_meaningful) if rules else set()
                    for fld in cf:
                        if fld in blanks_meaningful:
                            continue
                        val = row.fields.get(fld)
                        if val:
                            carry_state[fld] = str(val)
                            carry_source[fld] = row.row_id
                        elif fld in carry_state:
                            row.fields[fld] = carry_state[fld]
                            row.carried[fld] = carry_source[fld]
                    row.group_context = dict(group_context)
                    for fld, val in group_context.items():
                        if not row.fields.get(fld):
                            row.fields[fld] = val
                            row.carried.setdefault(fld, "group_heading")
                    if row.footnotes:
                        row.fields.setdefault("footnote_markers", " ".join(f"{k}:{v}" for k, v in sorted(row.footnotes.items())))
                    if not (row.fields.get("issuer") or row.fields.get("description")):
                        row.classification = "unknown"
                        row.notes.append("holding_without_descriptive_text")
                        holding_count -= 1
                    else:
                        holding_rows.append(row)
                rows_out.append(row)
        res = TableResult(
            table_index=ti,
            table_id=f"table_{ti}",
            score=round(score, 2),
            accepted=accepted,
            reasons=reasons,
            heading_text=nearest,
            heading_distance=heading_distance,
            detected_dates=dates,
            period_status=period_status,
            header_rows=header_n,
            flattened_headers=headers,
            column_mapping=mapping,
            column_mapping_rules=map_rules,
            scale_multiplier=mult,
            scale_source=mult_src,
            row_count=len(grid) - header_n,
            holding_rows=holding_count,
            total_rows=total_count,
            rows=rows_out,
            example_rows=[r.to_row() for r in rows_out if r.classification == "holding"][:max_example_rows],
        )
        results.append(res)
        state["prev_accepted"] = accepted
        state["after_total"] = after_total
        state["carry_state"], state["carry_source"], state["group_context"], state["column_currency"] = carry_state, carry_source, group_context, column_currency
        if accepted and header_n > 0 and grid:
            state["prev_layout"] = {"table_id": res.table_id, "table_index": ti, "raw_width": raw_width, "compression": compression, "merge_groups": merge_groups, "mapping": dict(mapping), "headers": list(headers)}
            layout_now = state["prev_layout"]
            for dti, dtable in list(deferred):
                deferred.remove((dti, dtable))
                process(dti, dtable, layout_now)  # a deferred header-less page adopts the next header page's layout
        elif accepted and inherited and prev_layout is not None:
            state["prev_layout"] = {**prev_layout, "table_index": ti}

    for ti, table in enumerate(tables):
        process(ti, table)
    state["draining"] = True
    for dti, dtable in list(deferred):
        process(dti, dtable, None)  # no matching layout ever appeared: scored and rejected normally
    results.sort(key=lambda r: r.table_index)
    holding_rows.sort(key=lambda r: (r.table_index, r.row_index))
    return HtmlExtraction(results, holding_rows, totals, doc_scale or default_scale, doc_scale_source)
