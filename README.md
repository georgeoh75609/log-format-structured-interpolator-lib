# log-format-structured-interpolator-lib

Parses printf-style log format strings (e.g. `"user %s logged in from %s"`) into a structured list of interpolation fields, each tagged with a positional index, raw spec, conversion letter, parsed flags/width/precision, and a coarse type bucket. Designed for observability pipelines that need to lift legacy log calls into key-value events.

```python
from log_format_structured_interpolator_lib import parse_format, FormatParseError

result = parse_format("user %s logged in, count=%d")
for field in result.fields:
    print(field.index, field.key, field.type, field.raw)
# 0 str string %s
# 1 int number %d
# literal_segments has len(fields)+1: prefix, between, suffix.
print(result.literal_segments)  # ['user ', ' logged in, count=', '']

try:
    parse_format("oops %")
except FormatParseError as e:
    print("bad format:", e)
```

## Why this exists

Observability backends want structured key-value events, but a large body of application code logs with printf-style format strings and positional arguments. Re-writing every call site is expensive and error-prone. This library sits at parse time — not emit time — so the format string itself can be analysed once and turned into a schema for the fields that will populate it at runtime.

The trade-off: we do not evaluate the arguments or produce a rendered string. Rendering belongs to the logger, not the parser. Keeping the two concerns separate means this library has zero runtime dependencies and never touches I/O, but it also means callers are responsible for aligning their argument list with `result.fields` by index.

## Conversion support

The supported conversion letters are: `d i o u x X e E f g G c s p`. That covers the specifiers that carry useful semantic type information for a downstream pipeline. `%n` and other niche/unsafe specifiers are rejected with `FormatParseError` rather than guessed at.

## The awkward edge

A bare `%` that is not part of a recognised specifier lands inside a `literal_segment`. Because printf has no formal escape other than `%%`, we treat `%%` as a literal percent within those segments and reject any other unescaped `%`. So `"100%% done %s"` parses cleanly (the `%%` stays in the literal segment), but `"value %"` and `"%z"` raise `FormatParseError`. If your format strings come from an untrusted source, wrap `parse_format` in a `try/except FormatParseError` and treat the failure as "keep this log line as raw text."

Precision with no digits (`%.s`) is preserved exactly as written: the `precision` field keeps the leading dot. This keeps round-tripping lossless for the raw spec, which matters for pipelines that re-emit the format string.
