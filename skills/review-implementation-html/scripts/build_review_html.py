"""Build a self-contained implementation-review HTML report."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from validate_review_report import validate_document  # noqa: E402


TOKEN = "{{REVIEW_DATA_JSON}}"


def safe_json_for_script(document: dict) -> str:
    """Serialize JSON so it cannot terminate its application/json script tag."""
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    return (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_html(document: dict, template: str) -> str:
    """Validate and embed review data into the static template."""
    errors = validate_document(document)
    if errors:
        raise ValueError("Invalid review data:\n- " + "\n- ".join(errors))
    if template.count(TOKEN) != 1:
        raise ValueError(f"Template must contain exactly one {TOKEN} token")
    return template.replace(TOKEN, safe_json_for_script(document))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=pathlib.Path, required=True)
    parser.add_argument("--template", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        document = json.loads(args.data.read_text(encoding="utf-8"))
        template = args.template.read_text(encoding="utf-8")
        rendered = render_html(document, template)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote review report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
