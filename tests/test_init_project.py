import shutil
import tomllib
from pathlib import Path

import pytest

from scripts import init_project

ROOT = Path(__file__).resolve().parent.parent


IGNORED = shutil.ignore_patterns(
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    ".schemathesis",
    ".coverage*",
    ".env",
    "requirements.txt",
    ".openapi-base.json",
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A scratch copy of the whole template, without caches and environments."""
    target = tmp_path / "project"
    shutil.copytree(ROOT, target, ignore=IGNORED)
    return target


def test_rename_moves_the_package_and_rewrites_every_name(project: Path) -> None:
    assert init_project.main(["orders-api", "--root", str(project)]) == 0

    assert (project / "src" / "orders_api" / "main.py").exists()
    assert not (project / "src" / "fastapi_szumplate").exists()
    for path in project.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".toml", ".md", ".example"}:
            text = path.read_text(encoding="utf-8")
            assert "fastapi_szumplate" not in text, path
            assert "fastapi-szumplate" not in text, path
    pyproject = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["name"] == "orders-api"
    assert pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/orders_api"]


def test_without_example_removes_the_domain_its_hook_settings_and_contracts(
    project: Path,
) -> None:
    assert init_project.main(["orders-api", "--without-example", "--root", str(project)]) == 0

    package = project / "src" / "orders_api"
    assert not (package / "library").exists()
    assert not (project / "tests" / "library").exists()
    assert "library" not in (package / "main.py").read_text(encoding="utf-8")
    config = (package / "config.py").read_text(encoding="utf-8")
    assert "loan_days" not in config
    assert "default_page_size" in config
    assert "LOAN" not in (project / ".env.example").read_text(encoding="utf-8")
    contracts = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]
    assert contracts
    assert all(".library" not in str(contract) for contract in contracts)


@pytest.mark.parametrize("flags", [[], ["--without-example"]], ids=["rename", "bare"])
def test_the_template_only_machinery_is_removed(project: Path, flags: list[str]) -> None:
    assert init_project.main(["orders-api", *flags, "--root", str(project)]) == 0

    assert not (project / "scripts" / "init_project.py").exists()
    assert not (project / "scripts" / "smoke_template.sh").exists()
    assert not (project / "tests" / "test_init_project.py").exists()
    ci = (project / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "template-smoke" not in ci
    assert "free-threaded" in ci
    makefile = (project / "Makefile").read_text(encoding="utf-8")
    assert "smoke" not in makefile
    readme = (project / "README.md").read_text(encoding="utf-8")
    assert "## Use it" not in readme
    assert "smoke-template" not in readme
    assert "## Run it" in readme


@pytest.mark.parametrize("flags", [[], ["--without-example"]], ids=["rename", "bare"])
def test_no_marker_comment_survives_in_the_project(project: Path, flags: list[str]) -> None:
    init_project.main(["orders-api", *flags, "--root", str(project)])

    for path in init_project.text_files(project):
        for line in path.read_text(encoding="utf-8").splitlines():
            assert init_project.MARKER.search(line) is None, f"{path}: {line}"


MARKED = """\
keep
<!-- begin:example -->
only with the example
<!-- end:example -->
<!-- begin:bare -->
only without it
<!-- begin:template -->
never
<!-- end:template -->
<!-- end:bare -->
| row | <!-- only:example -->
make: target  # only:bare
"""


@pytest.mark.parametrize(
    ("keep", "expected"),
    [
        ({"example"}, "keep\nonly with the example\n| row |\n"),
        ({"bare"}, "keep\nonly without it\nmake: target\n"),
        (set(), "keep\n"),
    ],
    ids=["example", "bare", "neither"],
)
def test_markers_keep_the_lines_of_the_chosen_audience(keep: set[str], expected: str) -> None:
    assert init_project.apply_markers(MARKED, frozenset(keep)) == expected


@pytest.mark.parametrize("name", ["Orders", "orders_api", "orders-", "1orders", ""])
def test_an_invalid_name_is_refused(project: Path, name: str) -> None:
    assert init_project.main([name, "--root", str(project)]) == 2
    assert (project / "src" / "fastapi_szumplate").exists()


def test_running_it_twice_is_refused(project: Path) -> None:
    init_project.main(["orders-api", "--root", str(project)])

    assert init_project.main(["billing-api", "--root", str(project)]) == 1
