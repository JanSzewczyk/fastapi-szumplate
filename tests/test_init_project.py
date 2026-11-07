import shutil
import tomllib
from pathlib import Path

import pytest

from scripts import init_project

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A scratch copy of the parts of the template the script touches."""
    ignore = shutil.ignore_patterns("__pycache__")
    shutil.copytree(ROOT / "src", tmp_path / "src", ignore=ignore)
    shutil.copytree(ROOT / "tests" / "library", tmp_path / "tests" / "library", ignore=ignore)
    for name in ("pyproject.toml", ".env.example", "README.md", "Makefile"):
        shutil.copy(ROOT / name, tmp_path / name)
    return tmp_path


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


@pytest.mark.parametrize("name", ["Orders", "orders_api", "orders-", "1orders", ""])
def test_an_invalid_name_is_refused(project: Path, name: str) -> None:
    assert init_project.main([name, "--root", str(project)]) == 2
    assert (project / "src" / "fastapi_szumplate").exists()


def test_running_it_twice_is_refused(project: Path) -> None:
    init_project.main(["orders-api", "--root", str(project)])

    assert init_project.main(["billing-api", "--root", str(project)]) == 1
