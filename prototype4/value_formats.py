"""value_formats.py - turn Grasshopper values into MATLAB literals.

No Grasshopper / Rhino / tkinter imports, so it works in Rhino, in the GUI window
and from a normal terminal.

Two layers
----------
1. BUILT-IN conversions (hard-coded edge cases, nothing to configure):
     5, 5.0, "5", " 5 "              ->  5
     True / "true"                   ->  true
     "hello"                         ->  'hello'        (quotes doubled: 'it''s')
     [1, 2, 3] / "1,2,3" / "1 2 3"   ->  [1 2 3]       (any length)
     "-1,0"  /  "(-1, 0)" / "<1,2>"  ->  [-1 0]        (coordinates)
     Point3d(1,2,3)                  ->  [1 2 3]       (anything with X, Y, Z)
     [[1,2],[3,4]] / "1,2;3,4"       ->  [1 2;3 4]     (matrix; ';' starts a new row)
     ["a", "b"]                      ->  {'a','b'}     (cell array of text)
     "nan" / "inf" / "-inf"          ->  NaN / Inf / -Inf
     [] / ""                         ->  [] / ''
2. YOUR formats (variable_formats.json, edited in the GUI window): rules such as
     "1 | 2 | 3"  ->  [1 2 3]
   Rules are checked first (ones that name their variables before general ones,
   each group top to bottom); the first that applies wins. If none applies, the
   built-in conversion is used.
"""
import json
import math
import os
import re
from fnmatch import fnmatchcase

from Capstone2.prototype4.matlab_literals import NUM, Literal, parse, quote, render, token_kind

FORMAT_VERSION = 1

OUTPUTS = [  # (key, label shown in the GUI)
    ("row", "Vector  [1 2 3]  (keeps MATLAB's row/column)"),
    ("column", "Column vector  [1;2;3]  (always a column)"),
    ("cell", "Cell array   {'a','b'}"),
    ("string_array", 'String array   ["a","b"]'),
    ("text", "One piece of text   'abc'"),
]
ITEM_MODES = [
    ("auto", "Numbers, or text if not a number"),
    ("number", "Numbers only"),
    ("text", "Text only"),
]
OUTPUT_KEYS = [k for k, _ in OUTPUTS]
ITEM_KEYS = [k for k, _ in ITEM_MODES]

DEFAULT_RULE = {
    "name": "New format",
    "enabled": True,
    "variables": "",
    "separator": "",
    "row_separator": "",
    "strip": "",
    "items": "auto",
    "output": "row",
}


# ----------------------------------------------------------- plain python
def _unwrap(x):
    """Grasshopper wrapper types (GH_Number, GH_String, ...) -> the value inside."""
    if type(x).__name__.startswith("GH_") and hasattr(x, "Value"):
        return x.Value
    return x


def to_plain(x):
    """Anything Grasshopper hands over -> None | bool | int | float | str | list.

    Points and vectors (anything with X and Y) become [x, y] / [x, y, z] lists, so
    the result can be saved as JSON and converted later.
    """
    x = _unwrap(x)
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if hasattr(x, "X") and hasattr(x, "Y"):
        try:
            coords = [float(x.X), float(x.Y)]
            if hasattr(x, "Z"):
                coords.append(float(x.Z))
            return coords
        except (TypeError, ValueError):
            pass
    if isinstance(x, dict):
        raise ValueError("a dictionary/struct can't be sent as one value; "
                         "send each field as its own variable (e.g. meteorite.IL)")
    if isinstance(x, (bytes, bytearray)):
        return x.decode("utf-8", "replace")
    try:
        return float(x)                    # Decimal, numpy numbers, System.Double ...
    except (TypeError, ValueError):
        pass
    try:
        return [to_plain(i) for i in x]    # list, tuple, .NET List<...>, generators
    except TypeError:
        return str(x)


# ------------------------------------------------------------------ tokens
def num_text(v):
    """Number -> MATLAB text."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    f = float(v)
    if math.isnan(f):
        return "NaN"
    if math.isinf(f):
        return "Inf" if f > 0 else "-Inf"
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return repr(f)


_NUM_FULL = re.compile(NUM)
_SPECIALS = {"nan": "NaN", "inf": "Inf", "+inf": "Inf", "-inf": "-Inf",
             "infinity": "Inf", "-infinity": "-Inf", "+infinity": "Inf"}


def number_token(text):
    """'5' / ' -1.5e3 ' / 'nan' -> MATLAB token, or None if it isn't a number."""
    t = str(text).strip()
    if _NUM_FULL.fullmatch(t):
        return num_text(float(t))
    return _SPECIALS.get(t.lower())


def _text_token(text):
    s = str(text)
    if "\n" in s or "\r" in s:
        raise ValueError("text contains a line break, which a MATLAB literal can't hold")
    return quote(s)


class M(object):
    """A MATLAB value under construction: rows of tokens plus the bracket type."""

    def __init__(self, rows, bracket="", sep=None):
        self.rows = rows
        self.bracket = bracket
        self.sep = sep

    @property
    def single(self):
        return not self.bracket and len(self.rows) == 1 and len(self.rows[0]) == 1

    def text(self):
        rows = self.rows
        if not rows:
            return "{}" if self.bracket == "{" else "[]"
        tokens = [t for r in rows for t in r]
        if self.bracket == "[" and len(tokens) == 1 and ":" not in tokens[0]:
            return tokens[0]                           # [5] is just 5
        if not self.bracket:
            return tokens[0]
        return render(Literal(rows, self.bracket, "", self.sep))


def _scalar(token):
    return M([[token]])


def _make(rows, sep=None):
    """Rows of tokens -> M: [..] when all are numbers/logicals, {..} when any is text."""
    if len({len(r) for r in rows}) > 1:
        raise ValueError("rows have different lengths (%s)"
                         % ", ".join(str(len(r)) for r in rows))
    has_text = any(token_kind(t) == "string" for r in rows for t in r)
    return M(rows, "{" if has_text else "[", sep or ("," if has_text else None))


# --------------------------------------------------------- built-in: text
_WRAPPERS = {"[": "]", "(": ")", "{": "}", "<": ">"}
_RANGE_TEXT = re.compile(r"\[?\s*(%s:%s(?::%s)?)\s*\]?" % (NUM, NUM, NUM))


def _simple_token(piece):
    """One item of a text list -> number / true / false token, else None."""
    tok = number_token(piece)
    if tok is not None:
        return tok
    if piece.lower() in ("true", "false"):
        return piece.lower()
    return None


def parse_text(s):
    """The built-in reading of text such as '5', '-1,0', '1 2 3', 'hello'."""
    t = s.strip()
    if not t:
        return _scalar("''")
    if t.lower() in ("true", "false"):
        return _scalar(t.lower())
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        inner = t[1:-1]
        if t[0] not in inner.replace(t[0] * 2, ""):
            return _scalar(_text_token(inner.replace(t[0] * 2, t[0])))
    tok = number_token(t)
    if tok is not None:
        return _scalar(tok)
    rng = _RANGE_TEXT.fullmatch(t)
    if rng:
        return M([[rng.group(1)]], "[")
    if t[0] in "[{":                                   # JSON-style nested lists
        try:
            data = json.loads(t)
        except ValueError:
            data = None
        if isinstance(data, list):
            return builtin(data)
    if t[0] in _WRAPPERS and t[-1] == _WRAPPERS[t[0]]:
        t = t[1:-1].strip()
    rows = []
    for line in re.split(r"[;\n]", t):
        line = line.strip()
        if not line:
            continue
        pieces = [p for p in re.split(r"[,\s]+", line) if p]
        tokens = [_simple_token(p) for p in pieces]
        if None in tokens:
            return _scalar(_text_token(s.strip()))
        rows.append(tokens)
    if not rows:
        return M([], "[")
    if len({len(r) for r in rows}) > 1:
        raise ValueError("rows have different lengths (%s)"
                         % ", ".join(str(len(r)) for r in rows))
    return M(rows, "[")


# ------------------------------------------------------- built-in: values
def builtin(value):
    """Plain python value -> M."""
    if value is None:
        raise ValueError("empty value (None)")
    if isinstance(value, bool):
        return _scalar("true" if value else "false")
    if isinstance(value, (int, float)):
        return _scalar(num_text(value))
    if isinstance(value, str):
        return parse_text(value)
    items = list(value)
    if not items:
        return M([], "[")
    parts = [builtin(i) for i in items]
    if all(p.single for p in parts):
        return _make([[p.rows[0][0] for p in parts]])
    if all(p.bracket and len(p.rows) == 1 for p in parts):      # a list of vectors
        return _make([p.rows[0] for p in parts])
    if all(p.single or (p.bracket and len(p.rows) == 1) for p in parts):
        raise ValueError("a list mixes single values and vectors")
    raise ValueError("lists are nested too deeply (only vectors and matrices are supported)")


# ------------------------------------------------------------------- rules
def normalize_rule(rule):
    out = dict(DEFAULT_RULE)
    out.update({k: rule[k] for k in DEFAULT_RULE if k in rule})
    out["enabled"] = bool(out["enabled"])
    for key in ("name", "variables", "separator", "row_separator", "strip"):
        out[key] = "" if out[key] is None else str(out[key])
    if out["items"] not in ITEM_KEYS:
        out["items"] = "auto"
    if out["output"] not in OUTPUT_KEYS:
        out["output"] = "row"
    return out


def rule_problems(rule):
    """List of reasons this rule can't work (empty list = fine)."""
    r = normalize_rule(rule)
    problems = []
    if not r["name"].strip():
        problems.append("it has no name")
    if r["output"] == "text":
        if not r["variables"].strip():
            problems.append("'One piece of text' must say which variables it applies to "
                            "(otherwise every variable would become text)")
    elif not (r["separator"] or r["row_separator"] or r["variables"].strip()):
        problems.append("it needs a separator or a list of variable names")
    if r["separator"] and r["separator"] == r["row_separator"]:
        problems.append("the item separator and the row separator are the same")
    return problems


def _unescape(s):
    return s.replace("\\t", "\t").replace("\\n", "\n")


def _name_patterns(rule):
    return [p.strip().lower() for p in rule["variables"].split(",") if p.strip()]


def rule_applies(rule, name, value):
    if not rule["enabled"]:
        return False
    patterns = _name_patterns(rule)
    if patterns and not any(fnmatchcase(name.lower(), p) for p in patterns):
        return False
    if rule["output"] == "text":
        return bool(patterns)
    if not isinstance(value, str):
        return False
    if patterns:
        return True
    return any(s and _unescape(s) in value for s in (rule["separator"], rule["row_separator"]))


def apply_rule(rule, value):
    """Convert one value with one rule. Returns M. Raises ValueError."""
    if rule["output"] == "text":
        if isinstance(value, (list, tuple)):
            return _make([[_text_token(v) for v in value]], ",") if value else M([], "{")
        return _scalar(_text_token(value))

    sep = _unescape(rule["separator"])
    row_sep = _unescape(rule["row_separator"])
    text = value.strip()
    if rule["strip"]:
        text = text.strip(rule["strip"] + " \t\r\n")

    mode = "text" if rule["output"] == "string_array" else rule["items"]
    rows = []
    for chunk in (text.split(row_sep) if row_sep else [text]):
        pieces = chunk.split(sep) if sep else chunk.split()
        pieces = [p.strip() for p in pieces]
        while pieces and not pieces[0]:
            pieces.pop(0)
        while pieces and not pieces[-1]:
            pieces.pop()
        if not pieces:
            continue
        tokens = []
        for k, p in enumerate(pieces, 1):
            if mode == "text":
                tokens.append(quote(p, '"') if rule["output"] == "string_array"
                              else _text_token(p))
                continue
            tok = _simple_token(p) if p else None
            if tok is None and mode == "number":
                raise ValueError("item %d (%r) is not a number" % (k, p))
            tokens.append(tok if tok is not None else _text_token(p))
        rows.append(tokens)
    if not rows:
        return M([], "{" if rule["output"] == "cell" else "[")

    if len({len(r) for r in rows}) > 1:
        raise ValueError("rows have different lengths (%s)" % ", ".join(str(len(r)) for r in rows))
    if rule["output"] == "string_array":
        return M(rows, "[", ",")
    if len(rows) == 1 and rule["output"] == "column":
        rows = [[t] for t in rows[0]]
    if rule["output"] == "cell":
        return M(rows, "{", ",")
    return _make(rows)


def convert(name, value, rules=None):
    """The one entry point. Returns (matlab_text, rule_name_or_None). Raises ValueError."""
    value = to_plain(value)
    if value is None:
        raise ValueError("empty value (None)")
    rules = list(rules or [])
    # A format that names its variables is more specific than a general one.
    rules = [r for r in rules if _name_patterns(r)] + [r for r in rules if not _name_patterns(r)]
    for rule in rules:
        if rule_applies(rule, name, value):
            try:
                return apply_rule(rule, value).text(), rule["name"]
            except ValueError as error:
                raise ValueError("format '%s': %s" % (rule["name"], error))
    return builtin(value).text(), None


def example_for(rule):
    """Sample Grasshopper text for a rule, and what it becomes: (input, output)."""
    r = normalize_rule(rule)
    if r["output"] == "text":
        return "007", "'007'"
    sep = _unescape(r["separator"])
    row_sep = _unescape(r["row_separator"])
    cell = r["output"] in ("cell", "string_array") or r["items"] == "text"
    items = ["a", "b", "c"] if cell else ["1", "2", "3"]
    pad = "" if sep.isspace() else " "
    glue = (pad + sep + pad) if sep else " "
    if row_sep:
        rows = [glue.join(items[:2]), glue.join(items[1:])]
        sample = (" " + row_sep + " ").join(rows)
    else:
        sample = glue.join(items)
    wrap = r["strip"][:2]
    if len(wrap) == 2:
        sample = wrap[0] + sample + wrap[1]
    name = (_name_patterns(r) or ["x"])[0].replace("*", "x")
    try:
        return sample, convert(name, sample, [dict(r, enabled=True)])[0]
    except ValueError as error:
        return sample, "error: %s" % error


# -------------------------------------------------------------------- file
def default_rules():
    return [normalize_rule({"name": "Pipe list  (1 | 2 | 3)", "separator": "|"})]


def load_rules(path, create=True):
    """Read variable_formats.json (made on first use). Raises ValueError if damaged."""
    if not os.path.isfile(path):
        rules = default_rules()
        if create:
            try:
                save_rules(path, rules)
            except OSError:
                pass
        return rules
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as error:
        raise ValueError("%s is not valid JSON (%s). Fix it, or delete the file to start "
                         "again." % (path, error))
    except OSError as error:
        raise ValueError("Can't read %s: %s" % (path, error))
    if isinstance(data, dict):
        data = data.get("rules", [])
    if not isinstance(data, list):
        raise ValueError("%s should contain a list of formats." % path)
    return [normalize_rule(r) for r in data if isinstance(r, dict)]


def save_rules(path, rules):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": FORMAT_VERSION, "rules": [normalize_rule(r) for r in rules]},
                  f, indent=2)
    os.replace(tmp, path)
