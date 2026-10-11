import json
from pathlib import Path

import pytest

SCHEMA = Path(__file__).resolve().parents[2] / "specs/001-change-impact-test-advisor/contracts/output-schema.json"


def test_report_matches_output_schema(project):
    jsonschema = pytest.importorskip("jsonschema")
    project.edit("include/door/state.h", "    int id;\n    bool locked;", "    bool locked;\n    int id;")
    project.edit("src/handlers.cpp", "    last = code;", "    last = code * 2;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    jsonschema.validate(r, json.loads(SCHEMA.read_text()))
    assert r["test_case_candidates"] and r["uncertainty_flags"]
