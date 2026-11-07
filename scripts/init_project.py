"""Turn a copy of this template into your project: rename it and, optionally, drop the example.

Run it once, in the root of the copy, before the first commit:

    python scripts/init_project.py orders-api
    python scripts/init_project.py orders-api --without-example

It renames the distribution (`fastapi-szumplate` -> `orders-api`), the package
(`fastapi_szumplate` -> `orders_api`) and its directory, and rewrites every text file. With
`--without-example` it also deletes the example domain (`library/`, `tests/library/`), its
`include_library` hook, its settings and its import-linter contracts. Afterwards run
`make openapi && make check`: the OpenAPI document carries the service name.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

OLD_DIST = "fastapi-szumplate"
OLD_PACKAGE = "fastapi_szumplate"
OLD_TITLE = "FastAPI Szumplate"

NAME_PATTERN = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*")
TEXT_SUFFIXES = {
    ".py",
    ".toml",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".lock",
    ".sh",
    ".example",
    ".txt",
}
TEXT_NAMES = {"Makefile", "Dockerfile", ".dockerignore", ".gitignore", ".pre-commit-config.yaml"}
SKIP_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
THIS_SCRIPT = Path(__file__).resolve()


def text_files(root: Path) -> list[Path]:
    """Return the files to rewrite: text files outside caches, without this script."""
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or SKIP_DIRS & set(path.relative_to(root).parts):
            continue
        if path.resolve() == THIS_SCRIPT:
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES:
            found.append(path)
    return found


def rename_project(root: Path, dist_name: str) -> None:
    """Rewrite names in every text file and move the package directory."""
    package = dist_name.replace("-", "_")
    title = " ".join(word.capitalize() for word in dist_name.split("-"))
    for path in text_files(root):
        text = path.read_text(encoding="utf-8")
        updated = (
            text.replace(OLD_PACKAGE, package)
            .replace(OLD_DIST, dist_name)
            .replace(OLD_TITLE, title)
        )
        if updated != text:
            path.write_text(updated, encoding="utf-8")
    old_dir = root / "src" / OLD_PACKAGE
    if old_dir.exists():
        old_dir.rename(root / "src" / package)


def remove_example(root: Path, package: str) -> None:
    """Delete the example domain and everything that points at it."""
    shutil.rmtree(root / "src" / package / "library", ignore_errors=True)
    shutil.rmtree(root / "tests" / "library", ignore_errors=True)

    main = root / "src" / package / "main.py"
    lines = main.read_text(encoding="utf-8").splitlines(keepends=True)
    main.write_text(
        "".join(line for line in lines if "include_library" not in line), encoding="utf-8"
    )

    config = root / "src" / package / "config.py"
    text = config.read_text(encoding="utf-8")
    text = re.sub(
        r"    (loans_max_active_per_member|loan_days): int = Field\(.*?\n    \)\n",
        "",
        text,
        flags=re.DOTALL,
    )
    config.write_text(text, encoding="utf-8")

    env_example = root / ".env.example"
    kept = [
        line
        for line in env_example.read_text(encoding="utf-8").splitlines(keepends=True)
        if not line.startswith(("LOANS_MAX_ACTIVE_PER_MEMBER", "LOAN_DAYS", "# Example domain"))
    ]
    env_example.write_text("".join(kept), encoding="utf-8")

    pyproject = root / "pyproject.toml"
    blocks = re.split(
        r"(?=^\[\[tool\.importlinter\.contracts\]\]$)",
        pyproject.read_text("utf-8"),
        flags=re.MULTILINE,
    )
    pyproject.write_text("".join(b for b in blocks if ".library" not in b), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments and run the steps."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "name", help="new distribution name, lowercase with dashes, e.g. orders-api"
    )
    parser.add_argument(
        "--without-example", action="store_true", help="also delete the example domain"
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: cwd)")
    args = parser.parse_args(argv)

    if not NAME_PATTERN.fullmatch(args.name):
        print(
            f"{args.name!r} is not a valid name: use lowercase letters, digits and dashes.",
            file=sys.stderr,
        )
        return 2
    root: Path = args.root.resolve()
    if not (root / "src" / OLD_PACKAGE).exists():
        print(
            f"No src/{OLD_PACKAGE} under {root}: was this project already renamed?", file=sys.stderr
        )
        return 1

    rename_project(root, args.name)
    if args.without_example:
        remove_example(root, args.name.replace("-", "_"))
    print(f"Renamed to {args.name}. Next: review the contact URL in openapi.py, then")
    print("  uv lock --check && make openapi && make check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
