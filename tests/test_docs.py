"""Documentation that can drift from the code is checked here."""

import re
from pathlib import Path

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parent.parent


def test_every_problem_type_is_in_the_reference(app: FastAPI) -> None:
    reference = (ROOT / "docs" / "reference" / "problem-types.md").read_text(encoding="utf-8")

    assert app.state.problem_types
    for kind in app.state.problem_types:
        assert f"`{kind.slug}`" in reference, kind.slug
        assert f"| {kind.status} |" in reference, kind.slug


def test_readme_lists_every_make_target() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    phony = re.search(r"^\.PHONY:(.*?)(?:\n\n|\Z)", makefile, re.DOTALL | re.MULTILINE)
    assert phony
    targets = phony.group(1).replace("\\", " ").split()

    assert targets
    for target in targets:
        assert f"make {target}" in readme, target
