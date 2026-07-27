import importlib.util
import pathlib
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


if __name__ == "__main__":
    unittest.main()
