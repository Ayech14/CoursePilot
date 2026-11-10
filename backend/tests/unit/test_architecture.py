"""Keeps the scheduling engine independent of the web and database layers."""

import ast
from pathlib import Path

import scheduler

FORBIDDEN = {
    "alembic",
    "app",
    "fastapi",
    "psycopg",
    "pydantic",
    "random",  # Plans must be reproducible.
    "secrets",
    "sqlalchemy",
    "starlette",
    "time",
}
# Reading the clock would make a plan depend on when it ran. `now` is passed in instead.
CLOCK_CALLS = {"now", "utcnow", "today"}


def forbidden_imports(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots = [node.module.split(".")[0]]
        else:
            continue
        found.update(root for root in roots if root in FORBIDDEN)
    return found


def test_detector_catches_violations() -> None:
    source = "import sqlalchemy.orm\nfrom app.models import Task\nfrom datetime import datetime\n"
    assert forbidden_imports(source) == {"sqlalchemy", "app"}


def test_scheduler_has_no_framework_imports() -> None:
    package_dir = Path(scheduler.__file__).parent
    violations = {
        str(path): imports
        for path in package_dir.rglob("*.py")
        if (imports := forbidden_imports(path.read_text()))
    }
    assert violations == {}


def clock_calls(source: str) -> set[str]:
    return {
        node.func.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in CLOCK_CALLS
    }


def test_clock_detector_catches_violations() -> None:
    assert clock_calls("from datetime import datetime\nx = datetime.now()\n") == {"now"}


def test_scheduler_never_reads_the_clock() -> None:
    package_dir = Path(scheduler.__file__).parent
    violations = {
        str(path): calls
        for path in package_dir.rglob("*.py")
        if (calls := clock_calls(path.read_text()))
    }
    assert violations == {}
