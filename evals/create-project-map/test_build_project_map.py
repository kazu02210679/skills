import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "create-project-map" / "scripts" / "build_project_map.py"
TEMPLATE = ROOT / "skills" / "create-project-map" / "assets" / "project-map-template.html"
SPEC = importlib.util.spec_from_file_location("build_project_map", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ProjectMapBuildTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
