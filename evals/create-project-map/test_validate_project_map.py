import importlib.util
import copy
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

    def v2(self):
        return copy.deepcopy(self.load("v2-map.json"))

    def assert_error(self, document, fragment):
        errors = MODULE.validate_document(document)
        self.assertTrue(
            any(fragment in error for error in errors),
            f"Expected {fragment!r} in {errors!r}",
        )

    def test_valid_document_has_no_errors(self):
        self.assertEqual(MODULE.validate_document(self.load("valid-map.json")), [])

    def test_missing_edge_target_is_reported(self):
        errors = MODULE.validate_document(self.load("invalid-edge-map.json"))
        self.assertTrue(any("missing-node" in error for error in errors))

    def test_v1_fixture_with_legacy_color_remains_valid(self):
        self.assertEqual(
            MODULE.validate_document(self.load("legacy-unsafe-color-map.json")),
            [],
        )

    def test_valid_v2_chain_contains_all_change_states(self):
        document = self.v2()
        self.assertEqual(MODULE.validate_document(document), [])
        comparison = document["comparisons"][0]
        for collection in ("Node", "Edge", "Flow"):
            keys = [
                f"{state}{collection}Ids"
                for state in (
                    "existing",
                    "inherited",
                    "changed",
                    "added",
                    "replaced",
                    "removed",
                )
            ]
            self.assertEqual(6, len(keys))
            self.assertTrue(all(isinstance(comparison[key], list) for key in keys))

    def test_rejects_future_schema_without_legacy_downgrade(self):
        document = self.v2()
        document["schemaVersion"] = 3
        self.assert_error(document, "schemaVersion")

    def test_explicit_schema_one_and_unknown_fields_preserve_legacy_rules(self):
        document = self.load("legacy-unsafe-color-map.json")
        document["schemaVersion"] = 1
        document["futureField"] = {"html": "<script>ignored</script>"}
        self.assertEqual(MODULE.validate_document(document), [])

    def test_rejects_invalid_v2_enums_and_color(self):
        cases = (
            (
                "view",
                lambda d: d["view"].update(defaultMode="journey"),
                "defaultMode",
            ),
            (
                "node kind",
                lambda d: next(
                    node for node in d["nodes"] if node["id"] == "api"
                ).update(kind="invalid"),
                "kind",
            ),
            (
                "edge kind",
                lambda d: next(
                    edge for edge in d["edges"] if edge["id"] == "api-calls-ui"
                ).update(kind="invalid"),
                "kind",
            ),
            (
                "change type",
                lambda d: next(
                    node for node in d["nodes"] if node["id"] == "api"
                ).update(changeType="moved"),
                "changeType",
            ),
            (
                "color",
                lambda d: d["categories"][0].update(color="url(javascript:bad)"),
                "color",
            ),
        )
        for _, mutate, fragment in cases:
            with self.subTest(fragment=fragment):
                document = self.v2()
                mutate(document)
                self.assert_error(document, fragment)

    def test_rejects_snapshot_cycles_duplicates_and_unknown_parents(self):
        document = self.v2()
        document["snapshots"][0]["parentId"] = "v16"
        self.assert_error(document, "cycle")

        document = self.v2()
        document["snapshots"].append(copy.deepcopy(document["snapshots"][0]))
        self.assert_error(document, "duplicate")

        document = self.v2()
        document["snapshots"][1]["parentId"] = "missing-snapshot"
        self.assert_error(document, "parentId")

    def test_rejects_bad_comparison_arrays_and_references(self):
        document = self.v2()
        document["comparisons"][0]["existingNodeIds"] = "api"
        self.assert_error(document, "existingNodeIds")

        document = self.v2()
        document["comparisons"][0]["addedNodeIds"] = ["missing-node"]
        self.assert_error(document, "comparison")

        document = self.v2()
        document["comparisons"][0]["existingNodeIds"].append("api")
        self.assert_error(document, "at most one")

        document = self.v2()
        document["currentSnapshotId"] = "missing-snapshot"
        self.assert_error(document, "currentSnapshotId")

        document = self.v2()
        document["view"]["defaultFlowId"] = "missing-flow"
        self.assert_error(document, "defaultFlowId")

        document = self.v2()
        document["view"]["availableModes"] = []
        self.assert_error(document, "availableModes")

    def test_rejects_v2_flow_edge_with_hidden_endpoint(self):
        document = self.v2()
        document["flows"][0]["edgeIds"].append("edge-to-external")
        self.assert_error(document, "flow.edgeIds")

    def test_rejects_invalid_replacement_reciprocity_and_removed_status(self):
        document = self.v2()
        document["nodes"][0].update(changeType="replaced", replacesId="missing-node")
        self.assert_error(document, "replacesId")

        document = self.v2()
        next(
            edge for edge in document["edges"] if edge["id"] == "api-calls-ui"
        ).update(changeType="replaced", replacesId="api")
        self.assert_error(document, "same collection")

        document = self.v2()
        old = next(node for node in document["nodes"] if node["id"] == "worker-v1")
        old["status"] = "planned"
        self.assert_error(document, "deprecated")

        document = self.v2()
        document["comparisons"][0]["removedNodeIds"] = ["api"]
        self.assert_error(document, "replacement")

    def test_rejects_non_tb_flow_layout(self):
        document = self.v2()
        document["view"]["layouts"]["flow"]["direction"] = "LR"
        self.assert_error(document, "direction")

        document = self.v2()
        document["view"]["layouts"]["flow"]["name"] = "grid"
        self.assert_error(document, "layout")

    def test_existing_finite_position_and_broken_edge_checks_remain(self):
        document = self.v2()
        document["nodes"][0]["position"]["x"] = float("nan")
        self.assert_error(document, "finite")
        self.assertTrue(
            any(
                "missing-node" in error
                for error in MODULE.validate_document(
                    self.load("invalid-edge-map.json")
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
