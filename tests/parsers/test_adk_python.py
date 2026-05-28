from pathlib import Path

from iam_legend.parsers.adk_python import ADKPythonParser

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "adk_python"


def test_matches_py_files_only():
    p = ADKPythonParser()
    assert p.matches("deploy.py") is True
    assert p.matches("main.tf") is False


def test_detects_basic_imports_and_calls():
    p = ADKPythonParser()
    out = p.parse_file(str(FIXTURE_DIR / "deploy_basic.py"))
    kinds = {r.kind for r in out}
    assert "aiplatform.vertex_init" in kinds
    assert "vertex.agent_engine_create" in kinds


def test_resolves_import_aliases():
    p = ADKPythonParser()
    out = p.parse_file(str(FIXTURE_DIR / "deploy_aliased.py"))
    kinds = {r.kind for r in out}
    assert "aiplatform.vertex_init" in kinds
    assert "aiplatform.endpoint_create" in kinds
    assert "vertex.agent_engine_create" in kinds


def test_line_numbers_populated():
    p = ADKPythonParser()
    out = p.parse_file(str(FIXTURE_DIR / "deploy_basic.py"))
    assert all(r.line > 0 for r in out)
