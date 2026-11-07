"""matlab_literals.py - read and write MATLAB literal values (no Grasshopper/tkinter).

A "literal" is the right-hand side of a simple assignment in a .m file:

    5            -2.5e3        NaN        Inf        true
    'text'       "text"        'it''s'
    [1 2 3]      [1, 2, 3]     [1;2;3]    [1 2;3 4]  [0:5:100]   [1 2 3]'
    {'a','b'}    {1,'x',true}  ["a","b"]  []         {}          ''

Arrays may span several lines (with or without "..."), and may be any length.
Anything else (v0 + a*t, zeros(3), linspace(...)) is a calculation, not a literal,
and is left alone.

Used by variable_transfer_v2.py (reading/writing .m files) and value_formats.py
(turning Grasshopper values into these literals).
"""
import re

NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
NAME = r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*"

_SQ = r"'(?:[^'\r\n]|'')*'"
_DQ = r'"(?:[^"\r\n]|"")*"'
_ATOM = rf"(?:{_SQ}|{_DQ}|(?:[-+]?(?:NaN|Inf)|true|false)(?![\w.])|{NUM}(?![\w.]))"
_RANGE = rf"{NUM}(?::{NUM}){{1,2}}"
_ELEM = re.compile(rf"(?:{_RANGE}|{_ATOM})(?=[\s,;%]|\.\.\.|$)")
_ATOM_FULL = re.compile(_ATOM)
_WRAP = re.compile(r"([\[\{])(.*)([\]\}])(\.?')?$", re.S)
_HEAD = re.compile(rf"^(\s*)({NAME})(\s*=(?!=)\s*)")

_PAIRS = {"[": "]", "{": "}"}


# ----------------------------------------------------------------- literals
class Literal(object):
    """A parsed literal.

    rows       list of rows, each a list of token strings exactly as written
    bracket    '' (single value), '[' or '{'
    transpose  '' or "'" or ".'"
    sep        separator between items on a row: ' ', ',' or ', '
    """

    def __init__(self, rows, bracket="", transpose="", sep=None):
        self.rows = rows
        self.bracket = bracket
        self.transpose = transpose
        self.sep = sep

    @property
    def kind(self):
        if not self.bracket:
            t = self.rows[0][0]
            if t[0] in "'\"":
                return "string"
            return "logical" if t in ("true", "false") else "number"
        return "cell" if self.bracket == "{" else "array"

    @property
    def count(self):
        return sum(len(r) for r in self.rows)


def token_kind(token):
    if token[:1] in ("'", '"'):
        return "string"
    return "logical" if token in ("true", "false") else "number"


def _tokenize(inner):
    """Inside [...] / {...} -> (rows, sep) or None if it isn't a plain literal."""
    rows, row = [], []
    sep = None
    i, n = 0, len(inner)
    last_end = None
    while i < n:
        c = inner[i]
        if c in " \t\r,":
            i += 1
            continue
        if c in ";\n":
            if row:
                rows.append(row)
                row = []
            last_end = None
            i += 1
            continue
        if inner.startswith("...", i):            # continuation: ignore rest of line
            nl = inner.find("\n", i)
            i = n if nl < 0 else nl + 1
            continue
        if c == "%":                              # comment inside a multi-line array
            nl = inner.find("\n", i)
            i = n if nl < 0 else nl
            continue
        m = _ELEM.match(inner, i)
        if not m:
            return None
        if row and sep is None and last_end is not None:
            gap = inner[last_end:i]
            sep = ("," if not gap.endswith(" ") else ", ") if "," in gap else " "
        row.append(m.group())
        last_end = m.end()
        i = m.end()
    if row:
        rows.append(row)
    return rows, sep


def parse(text):
    """Text -> Literal, or None if it is not a plain MATLAB literal."""
    t = str(text).strip()
    if not t:
        return None
    if _ATOM_FULL.fullmatch(t):
        return Literal([[t]])
    m = _WRAP.match(t)
    if not m or _PAIRS[m.group(1)] != m.group(3):
        return None
    if m.group(4) and m.group(1) == "{":
        return None
    parsed = _tokenize(m.group(2))
    if parsed is None:
        return None
    rows, sep = parsed
    return Literal(rows, m.group(1), m.group(4) or "", sep)


def is_literal(text):
    return parse(text) is not None


def render(lit, sep=None):
    """Literal -> one line of MATLAB text."""
    if not lit.bracket:
        return lit.rows[0][0]
    sep = sep or lit.sep or ("," if lit.bracket == "{" else " ")
    row_sep = ";" if sep in (" ", ",") else "; "
    inner = row_sep.join(sep.join(r) for r in lit.rows)
    return lit.bracket + inner + _PAIRS[lit.bracket] + lit.transpose


def normalize(text):
    """Same literal on one line, in its own style: '[1 2\\n 3 4]' -> '[1 2;3 4]'."""
    lit = parse(text)
    return render(lit) if lit else str(text).strip()


# ------------------------------------------------------------ text helpers
def unquote(token):
    q = token[0]
    return token[1:-1].replace(q + q, q)


def quote(text, q="'"):
    return q + str(text).replace(q, q + q) + q


def _is_column(lit):
    """True for [1;2;3] and for [1 2 3]'  (two or more items, standing up)."""
    if lit.count < 2 or not lit.bracket:
        return False
    stacked = len(lit.rows) >= 2 and all(len(r) == 1 for r in lit.rows)
    return stacked != bool(lit.transpose)


def restyle(new_text, old_text):
    """Give a new value the look of the value it replaces.

    The data never changes. What is copied from the old line:
      * the separator between items   ([1, 2, 3] vs [1 2 3])
      * the quote style of one string ('a' vs "a")
      * column orientation: a new plain list sent to [1;2;3] or [1 2 3]' stays a
        column (a matrix, or a list that is already a column, is left alone)
    """
    new, old = parse(new_text), parse(old_text)
    if new is None or old is None:
        return new_text
    if new.kind == "string" and old.kind == "string":
        q = old.rows[0][0][0]
        return quote(unquote(new.rows[0][0]), q)
    if not (new.bracket and new.bracket == old.bracket):
        return new_text

    sep = old.sep
    transpose = new.transpose
    rows = new.rows
    if len(rows) == 1 and len(rows[0]) >= 2 and not new.transpose and _is_column(old):
        if old.transpose:
            transpose = old.transpose           # [1 2 3]'  stays  [4 5 6]'
        else:
            rows = [[t] for t in rows[0]]       # [1;2;3]   stays  [4;5;6]
    if sep is None and rows is new.rows and transpose == new.transpose:
        return new_text
    return render(Literal(rows, new.bracket, transpose, new.sep), sep)


# ------------------------------------------------------------ file scanning
class Statement(object):
    """One 'name = literal' assignment found in a text file."""

    def __init__(self, start, end, indent, name, op, value, tail, newline, literal):
        self.start, self.end = start, end          # line numbers, inclusive
        self.indent, self.name, self.op = indent, name, op
        self.value, self.tail, self.newline = value, tail, newline
        self.literal = literal

    @property
    def text(self):
        return normalize(self.value)


def _split_eol(line):
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _read_value(lines, i, col):
    """Collect the value text of the assignment starting on line i at column col.

    Follows brackets and '...' onto following lines. Returns
    (value, tail, last_line_number, newline) or None.
    """
    buf = []
    li, pos = i, col
    depth = 0
    quote_char = None
    prev = " "
    while True:
        line, newline = _split_eol(lines[li])
        continued = False
        while pos < len(line):
            c = line[pos]
            if quote_char:
                buf.append(c)
                if c == quote_char:
                    if line[pos + 1:pos + 2] == quote_char:
                        buf.append(quote_char)
                        pos += 2
                        continue
                    quote_char = None
                prev = c
                pos += 1
                continue
            if c == '"' or (c == "'" and not (prev.isalnum() or prev in "_])}'.")):
                quote_char = c
            elif line.startswith("...", pos):
                buf.append(" ")
                continued = True
                break
            elif c in "([{":
                depth += 1
            elif c in ")]}":
                depth = max(depth - 1, 0)
            elif c in "%#":
                if depth == 0:
                    break
                break                      # comment inside a multi-line array
            elif c == ";" and depth == 0:
                break
            buf.append(c)
            prev = c
            pos += 1
        if depth > 0 or continued:
            li += 1
            if li >= len(lines):
                return None                # unfinished bracket
            pos = 0
            if not continued:
                buf.append("\n")
            prev = " "
            continue
        raw = "".join(buf)
        value = raw.rstrip()
        tail = raw[len(value):] + line[pos:]
        return value, tail, li, newline


def scan_statements(lines):
    """All 'name = literal' assignments in a list of lines (with line endings)."""
    found = []
    i = 0
    while i < len(lines):
        head = _HEAD.match(_split_eol(lines[i])[0])
        if not head:
            i += 1
            continue
        got = _read_value(lines, i, head.end())
        lit = parse(got[0]) if got else None
        if lit is None:
            i += 1
            continue
        value, tail, last, newline = got
        found.append(Statement(i, last, head.group(1), head.group(2), head.group(3),
                               value, tail, newline, lit))
        i = last + 1
    return found
