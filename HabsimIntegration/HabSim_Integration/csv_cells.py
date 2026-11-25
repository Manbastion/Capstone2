"""Update single cells of a structured CSV file (Transfer Variables CSV).

The CSV keeps its header row, its row order, its blank cells and every cell that
is not mapped. Each mapped variable overwrites ONE cell: the row is found by the
value of an identifier column (for example "Failure Mode (ID)" or "Index") and
the cell is the one under the named column.

Mapping lines (one per variable, e.g. typed into a Grasshopper Panel):

    variable | identifier column | identifier | column to change
    fan_repair_rate | Failure Mode (ID) | 5002001 | Repair Rate
    radiator_t2f    | Index             | 1       | T2F

Aliases for the identifier column: "id", "fmid", "failure mode" (-> Failure Mode (ID)).
Any other header of the CSV also works, matched without caring about case or spaces.
Plain Python 3.8+, no packages.
"""
import csv
import io
import math
import os
import re
import shutil
import tempfile
import time

_NAME = re.compile(r"^[A-Za-z_]\w*$")


# ---------------------------------------------------------------- reading
class Table(object):
    """A CSV held as a list of rows (lists of text) plus how it was written."""

    def __init__(self, rows, encoding, bom, newline, delimiter, final_newline):
        self.rows = rows
        self.encoding = encoding
        self.bom = bom
        self.newline = newline
        self.delimiter = delimiter
        self.final_newline = final_newline

    @property
    def header(self):
        return self.rows[0] if self.rows else []


def read_table(path):
    """Read a CSV so it can be written back the way it was."""
    with open(path, "rb") as stream:
        raw = stream.read()
    if not raw.strip():
        raise ValueError("The CSV file is empty: %s" % path)

    bom = raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:] if bom else raw
    try:
        text, encoding = body.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        text, encoding = body.decode("cp1252", "replace"), "cp1252"

    newline = "\r\n" if "\r\n" in text else "\n"
    first_line = text.split("\n", 1)[0]
    delimiter = max((",", ";", "\t"), key=first_line.count)
    if first_line.count(delimiter) == 0:
        delimiter = ","
    final_newline = text.endswith("\n")

    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    if not rows or not any(cell.strip() for cell in rows[0]):
        raise ValueError("The first row of the CSV must be a header row: %s" % path)
    return Table(rows, encoding, bom, newline, delimiter, final_newline)


def render_table(table):
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=table.delimiter, lineterminator=table.newline,
                        quoting=csv.QUOTE_MINIMAL)
    writer.writerows(table.rows)
    text = out.getvalue()
    if not table.final_newline and text.endswith(table.newline):
        text = text[:-len(table.newline)]
    data = text.encode(table.encoding, "replace")
    return (b"\xef\xbb\xbf" + data) if table.bom else data


def write_table(path, table):
    """Replace the file safely (write a temp file, then swap it in)."""
    data = render_table(table)
    folder = os.path.dirname(os.path.abspath(path))
    fd, temp = tempfile.mkstemp(prefix=".csvcells_", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        last = None
        for _ in range(20):                      # Windows: another program may hold the file briefly
            try:
                os.replace(temp, path)
                return
            except PermissionError as error:
                last = error
                time.sleep(0.1)
        raise PermissionError(
            "Could not write %s - is it open in Excel? Close it and try again. (%s)" % (path, last))
    finally:
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                pass


# ---------------------------------------------------------------- headers
def _norm(text):
    return re.sub(r"\s+", " ", str(text)).strip().casefold()


_ALIASES = {
    "id": "failure mode", "fmid": "failure mode", "fm id": "failure mode",
    "failure mode": "failure mode", "failure mode id": "failure mode",
    "failuremode": "failure mode",
}


def resolve_column(header, wanted):
    """Header name (any case/spacing, or an alias) -> column position."""
    key = _norm(wanted)
    names = [_norm(h) for h in header]
    if key in names:
        return names.index(key)
    alias = _ALIASES.get(key)
    if alias:
        for i, name in enumerate(names):
            if name.startswith(alias):
                return i
    near = [h.strip() for h in header if key and key in _norm(h)]
    hint = (" Did you mean: %s?" % ", ".join(near)) if near else ""
    raise ValueError("Column %r was not found in the CSV header. Columns are: %s.%s"
                     % (str(wanted).strip(), ", ".join(h.strip() or "<blank>" for h in header), hint))


# ---------------------------------------------------------------- mapping
class Link(object):
    def __init__(self, variable, id_column, identifier, column):
        self.variable = variable
        self.id_column = id_column          # column position
        self.identifier = identifier        # text
        self.column = column                # column position


def mapping_lines(raw):
    """Panel text, a list of lines, or a nested list -> clean mapping lines."""
    if raw is None:
        return []
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    lines = []
    for item in items:
        for line in str(item).splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "//")):
                lines.append(line)
    return lines


def parse_mapping(raw, header):
    """Mapping text -> list of Link, with a clear error for any bad line."""
    links, seen = [], {}
    for line in mapping_lines(raw):
        parts = [p.strip() for p in (line.split("|") if "|" in line else line.split("\t"))]
        if len(parts) != 4 or not all(parts):
            raise ValueError(
                "Mapping line %r needs 4 parts separated by |:  "
                "variable | identifier column | identifier | column to change" % line)
        variable, id_name, identifier, column_name = parts
        if not _NAME.match(variable):
            raise ValueError("%r is not a valid variable name (letters, digits, _; not starting "
                             "with a digit)." % variable)
        link = Link(variable, resolve_column(header, id_name), identifier,
                    resolve_column(header, column_name))
        cell = (link.id_column, identifier, link.column)
        if variable in seen:
            raise ValueError("Variable %r is mapped twice." % variable)
        for other in links:
            if (other.id_column, other.identifier, other.column) == cell:
                raise ValueError("%r and %r both write to the same cell (%s = %s, %s)."
                                 % (other.variable, variable, id_name, identifier, column_name))
        seen[variable] = True
        links.append(link)
    if not links:
        raise ValueError("The mapping is empty. Add one line per variable: "
                         "variable | identifier column | identifier | column to change")
    return links


# ---------------------------------------------------------------- values
def format_value(value):
    """Python value -> text for a CSV cell."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("NaN/infinity can't be written to the CSV.")
        return format(value, ".15g")
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(format_value(v) for v in value) + "]"
    return str(value)


def _same_id(cell, identifier):
    a, b = cell.strip(), identifier.strip()
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def find_row(table, link):
    matches = [i for i in range(1, len(table.rows))
               if link.id_column < len(table.rows[i])
               and _same_id(table.rows[i][link.id_column], link.identifier)]
    id_name = table.header[link.id_column].strip()
    if not matches:
        raise ValueError("No row with %s = %s for variable %r." % (id_name, link.identifier, link.variable))
    if len(matches) > 1:
        raise ValueError("%d rows have %s = %s (variable %r). The identifier must be unique; "
                         "use a different identifier column." % (len(matches), id_name, link.identifier, link.variable))
    return matches[0]


def locate(table, links):
    """[(link, row position)] - raises if any identifier is missing or ambiguous."""
    plan, used = [], {}
    for link in links:
        row = find_row(table, link)
        cell = (row, link.column)
        if cell in used:                 # e.g. one line by Index, another by Failure Mode (ID)
            raise ValueError("%r and %r both write to the same cell (row %d, %s)."
                             % (used[cell], link.variable, row + 1, table.header[link.column].strip()))
        used[cell] = link.variable
        plan.append((link, row))
    return plan


# ---------------------------------------------------------------- the transfer
def preview(path, mapping_raw, values=None):
    """Check the mapping against the file without changing it. Returns report lines."""
    table = read_table(path)
    links = parse_mapping(mapping_raw, table.header)
    lines = []
    for link, row in locate(table, links):
        old = table.rows[row][link.column] if link.column < len(table.rows[row]) else ""
        new = ""
        if values is not None and link.variable in values:
            new = "  ->  %s" % format_value(values[link.variable])
        lines.append("%s : row %d, %s = %r%s" % (
            link.variable, row + 1, table.header[link.column].strip(), old, new))
    return lines


def transfer_cells(path, mapping_raw, values, backup=True):
    """Write the mapped variables into their CSV cells.

    values : {variable: python value} - the current iteration's values.
    Returns (report_lines, [variables that had no value]). Nothing is written if any
    part of the mapping is wrong.
    """
    table = read_table(path)
    links = parse_mapping(mapping_raw, table.header)
    missing = [l.variable for l in links if l.variable not in values]
    if missing:
        raise ValueError("The mapping uses variables that have no value (not in Names): %s"
                         % ", ".join(missing))
    plan = locate(table, links)                       # check everything before writing anything
    new_text = {l.variable: format_value(values[l.variable]) for l, _ in plan}

    lines = []
    for link, row in plan:
        cells = table.rows[row]
        if len(cells) <= link.column:
            cells.extend([""] * (link.column + 1 - len(cells)))
        old = cells[link.column]
        cells[link.column] = new_text[link.variable]
        lines.append("%s -> row %d (%s = %s), %s : %s -> %s" % (
            link.variable, row + 1, table.header[link.id_column].strip(), link.identifier,
            table.header[link.column].strip(), old or "<blank>", new_text[link.variable] or "<blank>"))

    if backup:
        original = path + ".original"
        if not os.path.exists(original):
            shutil.copy2(path, original)
            lines.append("note: saved your untouched CSV as %s" % os.path.basename(original))
    write_table(path, table)
    return lines, []
