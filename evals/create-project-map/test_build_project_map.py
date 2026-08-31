import copy
from html.parser import HTMLParser
import importlib.util
import json
import pathlib
import re
import tempfile
import unittest
from urllib.parse import quote, unquote


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "create-project-map" / "scripts" / "build_project_map.py"
TEMPLATE = ROOT / "skills" / "create-project-map" / "assets" / "project-map-template.html"
SPEC = importlib.util.spec_from_file_location("build_project_map", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class _AnchorHrefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self._in_anchor = False
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self._in_anchor = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_anchor = False

    def handle_data(self, data):
        if self._in_anchor:
            self.text.append(data)


class ProjectMapBuildTests(unittest.TestCase):
    def test_cases_include_v2_browser_and_large_flow_cases(self):
        cases = json.loads(
            (ROOT / "evals" / "create-project-map" / "cases.json").read_text(encoding="utf-8")
        )
        by_id = {case["id"]: case for case in cases}
        expected = {
            "v2-snapshot-comparison",
            "v2-mode-and-edge-authority",
            "legacy-v1-compatibility",
            "large-flow-bounded-layout",
        }
        self.assertTrue(expected <= set(by_id))
        self.assertEqual(100, by_id["large-flow-bounded-layout"]["expect"]["node_count"])

    def test_render_replaces_tokens_and_escapes_text(self):
        document = {"project": {"title": "<Map>", "summary": "A & B"}}
        rendered = MODULE.render_html(
            document,
            "<title>{{PROJECT_TITLE}}</title><p>{{PROJECT_SUMMARY}}</p><b>{{DATA_FILENAME}}</b>",
            "architecture-map.json",
        )
        self.assertIn("&lt;Map&gt;", rendered)
        self.assertIn("A &amp; B", rendered)
        self.assertIn("architecture-map.json", rendered)
        self.assertNotIn("{{PROJECT_", rendered)

    def test_template_exposes_interactive_map_controls(self):
        rendered = MODULE.render_html(
            {"project": {"title": "Map", "summary": "Summary"}},
            TEMPLATE.read_text(encoding="utf-8"),
            "architecture-map.json",
        )
        for marker in ('id="cy"', 'id="flowNav"', 'id="nodeSearch"', 'id="fitButton"'):
            self.assertIn(marker, rendered)

    def test_v2_metadata_is_not_embedded_as_html_or_javascript(self):
        document = {
            "schemaVersion": 2,
            "project": {
                "title": "</title><script>alert(1)</script>",
                "summary": "</script><script>owned()</script>",
            },
            "comparisons": [{"summary": "<img src=x onerror=owned()>"}],
        }
        before = copy.deepcopy(document)
        rendered = MODULE.render_html(
            document,
            "<title>{{PROJECT_TITLE}}</title><p>{{PROJECT_SUMMARY}}</p><a href=\"{{DATA_FILENAME}}\">JSON</a>",
            "../data/architecture-map.json",
        )
        self.assertEqual(before, document)
        self.assertNotIn("</script>", rendered.lower())
        self.assertNotIn("<script>", rendered.lower())
        self.assertNotIn("<img", rendered.lower())
        self.assertIn("../data/architecture-map.json", rendered)

    def test_relative_data_filename_uses_posix_relative_path(self):
        data = pathlib.Path("C:/repo/maps/architecture-map.json")
        output = pathlib.Path("C:/repo/maps/html/architecture-map.html")
        self.assertEqual(
            "../architecture-map.json",
            MODULE.relative_data_filename(data, output),
        )

    def test_invalid_document_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            data = root / "invalid.json"
            template = root / "template.html"
            output = root / "architecture-map.html"
            data.write_text(json.dumps({"schemaVersion": 2}), encoding="utf-8")
            template.write_text("<html>{{PROJECT_TITLE}}</html>", encoding="utf-8")
            output.write_text("old rendered map", encoding="utf-8")
            result = MODULE.main([
                "--data", str(data),
                "--template", str(template),
                "--output", str(output),
            ])
            self.assertEqual(1, result)
            self.assertEqual("old rendered map", output.read_text(encoding="utf-8"))

    def test_data_filename_escaping_matches_html_and_javascript_contexts(self):
        data_filename = 'folder/& "日本語"/</script>\u2028\u2029.json'
        expected_url = quote(data_filename, safe="/")
        rendered = MODULE.render_html(
            {"project": {"title": "Map", "summary": "Summary"}},
            '<a href="{{DATA_FILENAME_URL}}">{{DATA_FILENAME_TEXT}}</a><script>const DATA_URL = {{DATA_FILENAME_JS}};</script>',
            data_filename,
        )

        parser = _AnchorHrefParser()
        parser.feed(rendered)
        self.assertEqual(data_filename, "".join(parser.text))
        self.assertEqual(expected_url, parser.href)
        self.assertEqual(data_filename, unquote(parser.href))
        javascript_match = re.search(r"const DATA_URL = (.+);", rendered)
        self.assertIsNotNone(javascript_match)
        javascript_literal = javascript_match.group(1)
        self.assertEqual(expected_url, json.loads(javascript_literal))
        self.assertNotIn("</script>", javascript_literal.lower())
        self.assertNotIn("<", javascript_literal)
        self.assertNotIn(">", javascript_literal)
        self.assertNotIn("&", javascript_literal)

    def test_data_filename_url_encoding_preserves_names_and_separators(self):
        names = (
            "architecture-map.json",
            "../architecture-map.json",
            "map#v2.json",
            "map%v2.json",
            "map?v2.json",
            "folder/space name_日本.json",
            "folder/a&b.json",
        )
        template = '<a href="{{DATA_FILENAME_URL}}">{{DATA_FILENAME_TEXT}}</a><script>const DATA_URL = {{DATA_FILENAME_JS}};</script>'
        for data_filename in names:
            with self.subTest(data_filename=data_filename):
                rendered = MODULE.render_html(
                    {"project": {"title": "Map", "summary": "Summary"}},
                    template,
                    data_filename,
                )
                parser = _AnchorHrefParser()
                parser.feed(rendered)
                expected_url = quote(data_filename, safe="/")
                self.assertEqual(data_filename, "".join(parser.text))
                self.assertEqual(expected_url, parser.href)
                self.assertEqual(data_filename, unquote(parser.href))
                javascript_match = re.search(r"const DATA_URL = (.+);", rendered)
                self.assertIsNotNone(javascript_match)
                self.assertEqual(expected_url, json.loads(javascript_match.group(1)))


if __name__ == "__main__":
    unittest.main()
