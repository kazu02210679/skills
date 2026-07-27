from __future__ import annotations

import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "review-implementation-html"
SCRIPT = SKILL / "scripts" / "build_review_html.py"
TEMPLATE = SKILL / "assets" / "review-template.html"
FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "valid-review.json"
SPEC = importlib.util.spec_from_file_location("build_review_html", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ReviewHtmlBuildTests(unittest.TestCase):
    @staticmethod
    def valid_review() -> dict:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_script_json_escapes_html_terminators(self):
        payload = MODULE.safe_json_for_script(
            {"text": "</script><script>alert(1)</script>"}
        )
        self.assertNotIn("</script>", payload.lower())
        self.assertIn("\\u003c", payload)

    def test_render_contains_comment_and_export_controls(self):
        rendered = MODULE.render_html(
            self.valid_review(), TEMPLATE.read_text(encoding="utf-8")
        )
        for marker in (
            'id="reviewNav"',
            "data-comment-id",
            'id="exportComments"',
            'id="copyCorrectionPrompt"',
            'id="manualCopyFallback"',
        ):
            self.assertIn(marker, rendered)

    def test_export_uses_attached_download_link_and_reports_completion(self):
        rendered = MODULE.render_html(
            self.valid_review(), TEMPLATE.read_text(encoding="utf-8")
        )
        self.assertIn("document.body.append(anchor)", rendered)
        self.assertIn('status.textContent = "Exported"', rendered)


if __name__ == "__main__":
    unittest.main()
