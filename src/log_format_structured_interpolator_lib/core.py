import re
from dataclasses import dataclass
from typing import List

# Pattern explanation:
# - %% is handled first as a literal percent escape.
# - %[flags][width][.precision]type
# Flags: any run of +- #0 . Width: optional digits. Precision: . optional digits.
# Type: one of the explicitly supported set. We anchor the type to a fixed
# character class so that unsupported types like %n fail loudly.
_FIELD_RE = re.compile(
    r"""
    %
    ( [-+ #0]* )           # flags
    ( \d* )                # width
    ( \.\d* )?             # precision (dot + optional digits)
    ( [diouxXeEfgGcps] )   # conversion type
    """,
    re.VERBOSE,
)

# Supported conversion specifiers and a human label for each. The label is
# used as the synthetic key name when the format string gives no positional
# hint. This is the only place that maps a letter to a meaning.
_SPECIFIER_KIND = {
    "d": "int",
    "i": "int",
    "o": "oct",
    "u": "uint",
    "x": "hex",
    "X": "hex_upper",
    "e": "float_exp",
    "E": "float_exp_upper",
    "f": "float",
    "g": "float_g",
    "G": "float_g_upper",
    "c": "char",
    "s": "str",
    "p": "pointer",
}

# Conversion specifiers that take a string-typed argument. Used to populate the
# `type` field on the produced Field so downstream consumers know what to cast
# to. int-family -> "number", float-family -> "number", str/char -> "string".
_STRING_TYPES = {"c", "s", "p"}
_INT_TYPES = {"d", "i", "o", "u", "x", "X"}


class FormatParseError(ValueError):
    """Raised when a format string contains a spec we cannot safely parse."""


@dataclass
class Field:
    """One interpolated slot in a parsed format string.

    Attributes:
        index: Zero-based positional index among interpolation fields, matching
            the order of positional arguments.
        raw: The exact substring from the format string, including the leading
            % and any flags/width/precision. Preserved verbatim so a consumer
            that needs byte-exact reconstruction has the source slice.
        spec: The conversion letter (e.g. "s", "d").
        flags, width, precision: Parsed decorations. Precision keeps its
            leading dot when present, as the literal substring, because empty
            precision ("%.s") is meaningful in printf and discarding the dot
            would erase it.
        key: The synthetic key name for this field. See _SPECIFIER_KIND.
        type: Coarse type bucket ("number" | "string") for downstream casting.
    """

    index: int
    raw: str
    spec: str
    flags: str
    width: str
    precision: str
    key: str
    type: str


@dataclass
class ParseResult:
    """Full result of parsing a format string.

    `literal_segments` has len(fields) + 1 entries: the text before the first
    field, the text between each pair of fields, and the trailing text. This
    way a consumer can interleave literal_segments[i] + the formatted value of
    fields[i] to reconstruct the message, and literal_segments[-1] is the tail.
    """

    fields: List[Field]
    literal_segments: List[str]


def parse_format(fmt: str) -> ParseResult:
    """Parse a printf-style format string into structured fields.

    Accepts %<flags><width>.<precision><type> for the conversion letters in
    _SPECIFIER_KIND and %% as a literal percent. Everything else is a literal.

    Raises FormatParseError on a malformed or unsupported specifier so the
    caller can decide whether to fall back to raw text or surface the error.
    """
    if not isinstance(fmt, str):
        raise TypeError("fmt must be a str")

    fields: List[Field] = []
    segments: List[str] = []
    pos = 0
    idx = 0

    # We must collapse %% into a single placeholder percent *before* running
    # the field regex, so that a %% adjacent to a real field (e.g. "%%prefix%s")
    # is not misparsed. We replace %% with a single \x00 byte (which cannot
    # appear in a Python str format string) and then restore it after parsing.
    ESC = "\x00"
    collapsed = fmt.replace("%%", ESC)

    for m in _FIELD_RE.finditer(collapsed):
        literal = collapsed[pos:m.start()]
        segments.append(literal.replace(ESC, "%%"))

        flags, width, precision, spec = m.group(1), m.group(2), m.group(3) or "", m.group(4)

        fields.append(
            Field(
                index=idx,
                raw=m.group(0),
                spec=spec,
                flags=flags,
                width=width,
                precision=precision,
                key=_SPECIFIER_KIND[spec],
                type="string" if spec in _STRING_TYPES else "number",
            )
        )
        idx += 1
        pos = m.end()
    # Trailing literal after the last field (or the whole string if none).
    segments.append(collapsed[pos:].replace(ESC, "%%"))

    # Validate and reject stray % that did not match the field pattern. We do
    # a single pass over the literal segments so we catch a bare "%" that the
    # field regex skipped (e.g. "%!" or a lone "%" at EOS).
    _check_literals(segments)

    return ParseResult(fields=fields, literal_segments=segments)


def _check_literals(segments: List[str]) -> None:
    """Reject unsupported specifiers that appear inside literal segments.

    A bare "%" or "%<unknown>" in the format string is not matched by
    _FIELD_RE, so it lands in a literal segment. We scan those segments for
    any unescaped "%" and raise so callers do not silently lose arguments.
    """
    for seg in segments:
        i = 0
        while i < len(seg):
            ch = seg[i]
            if ch == "%":
                # %% is an escaped percent — advance past the pair.
                if i + 1 < len(seg) and seg[i + 1] == "%":
                    i += 2
                    continue
                raise FormatParseError(
                    f"unsupported or unterminated specifier at offset {i!r} in segment {seg!r}"
                )
            i += 1
