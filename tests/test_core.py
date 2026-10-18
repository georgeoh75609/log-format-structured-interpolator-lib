import unittest

from log_format_structured_interpolator_lib import FormatParseError, parse_format
from log_format_structured_interpolator_lib.core import ParseResult


class TestParseFormat(unittest.TestCase):
    def test_plain_string_has_no_fields(self):
        r = parse_format("hello world")
        self.assertEqual(r.fields, [])
        self.assertEqual(r.literal_segments, ["hello world"])

    def test_single_string_spec(self):
        r = parse_format("hello %s")
        self.assertEqual(len(r.fields), 1)
        f = r.fields[0]
        self.assertEqual(f.index, 0)
        self.assertEqual(f.raw, "%s")
        self.assertEqual(f.spec, "s")
        self.assertEqual(f.key, "str")
        self.assertEqual(f.type, "string")
        self.assertEqual(r.literal_segments, ["hello ", ""])

    def test_multiple_specs_indexed(self):
        r = parse_format("%s %d %s")
        self.assertEqual([f.index for f in r.fields], [0, 1, 2])
        self.assertEqual([f.spec for f in r.fields], ["s", "d", "s"])
        self.assertEqual(r.literal_segments, ["", " ", " ", ""])

    def test_int_family_keys(self):
        r = parse_format("%d %i %o %u %x %X")
        self.assertEqual(
            [f.key for f in r.fields],
            ["int", "int", "oct", "uint", "hex", "hex_upper"],
        )
        for f in r.fields:
            self.assertEqual(f.type, "number")

    def test_float_family_keys(self):
        r = parse_format("%e %E %f %g %G")
        self.assertEqual(
            [f.key for f in r.fields],
            ["float_exp", "float_exp_upper", "float", "float_g", "float_g_upper"],
        )
        for f in r.fields:
            self.assertEqual(f.type, "number")

    def test_char_and_pointer_are_string_typed(self):
        r = parse_format("%c %p")
        self.assertEqual([f.key for f in r.fields], ["char", "pointer"])
        self.assertEqual([f.type for f in r.fields], ["string", "string"])

    def test_flags_width_precision_preserved_in_raw(self):
        r = parse_format("%08.2f")
        f = r.fields[0]
        self.assertEqual(f.raw, "%08.2f")
        self.assertEqual(f.flags, "0")
        self.assertEqual(f.width, "8")
        self.assertEqual(f.precision, ".2")
        self.assertEqual(f.spec, "f")

    def test_multiple_flags(self):
        r = parse_format("%+-0#x")
        f = r.fields[0]
        self.assertEqual(f.flags, "+-0#")
        self.assertEqual(f.spec, "x")

    def test_precision_without_digits(self):
        # %.s is legal printf meaning precision 0. The dot must be kept so a
        # round-tripper can reproduce it exactly.
        r = parse_format("%.s")
        f = r.fields[0]
        self.assertEqual(f.precision, ".")
        self.assertEqual(f.width, "")
        self.assertEqual(f.raw, "%.s")

    def test_percent_escape_in_literal(self):
        r = parse_format("100%% done %s")
        self.assertEqual(len(r.fields), 1)
        self.assertEqual(r.fields[0].spec, "s")
        self.assertEqual(r.literal_segments, ["100%% done ", ""])

    def test_leading_and_trailing_percent_escape(self):
        r = parse_format("%%prefix%s%%")
        self.assertEqual(len(r.fields), 1)
        self.assertEqual(r.literal_segments, ["%%prefix", "%%"])

    def test_unterminated_percent_raises(self):
        with self.assertRaises(FormatParseError):
            parse_format("value %")

    def test_unknown_specifier_raises(self):
        with self.assertRaises(FormatParseError):
            parse_format("%z")

    def test_unknown_specifier_after_field_raises(self):
        with self.assertRaises(FormatParseError):
            parse_format("%s and then %q")

    def test_non_string_input_raises_type_error(self):
        with self.assertRaises(TypeError):
            parse_format(123)  # type: ignore[arg-type]

    def test_empty_string(self):
        r = parse_format("")
        self.assertEqual(r.fields, [])
        self.assertEqual(r.literal_segments, [""])

    def test_literal_only_with_percent_escape(self):
        r = parse_format("50%% off")
        self.assertEqual(r.fields, [])
        self.assertEqual(r.literal_segments, ["50%% off"])

    def test_segments_count_is_fields_plus_one(self):
        r = parse_format("%s%d%s")
        self.assertEqual(len(r.literal_segments), len(r.fields) + 1)

    def test_result_is_parse_result_instance(self):
        r = parse_format("%s")
        self.assertIsInstance(r, ParseResult)


if __name__ == "__main__":
    unittest.main()
