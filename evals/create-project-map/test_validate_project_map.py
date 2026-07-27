import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "create-project-map" / "scripts" / "validate_project_map.py"
SPEC = importlib.util.spec_from_file_location("validate_project_map", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ProjectMapValidationTests(unittest.TestCase):
    def load(self, name):
        path = pathlib.Path(__file__).parent / "fixtures" / name
        return json.loads(path.read_text(encoding="utf-8"))

    def test_valid_document_has_no_errors(self):
        self.assertEqual(MODULE.validate_document(self.load("valid-map.json")), [])

    def test_missing_edge_target_is_reported(self):
        errors = MODULE.validate_document(self.load("invalid-edge-map.json"))
        self.assertTrue(any("missing-node" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
