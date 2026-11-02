"""Every third-party module the app imports must be a runtime dependency, not a dev-only one
(httpx once was, and the production container crashed on start)."""
import ast
import re
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, packages_distributions, requires
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _parse(req: str) -> tuple[str, set[str]]:
    """'uvicorn[standard]>=0.30; python_version>"3"' -> ('uvicorn', {'standard'})"""
    req = req.split(";")[0]
    m = re.match(r"\s*([A-Za-z0-9_.-]+)\s*(?:\[([^\]]*)\])?", req)
    return m.group(1).lower().replace("_", "-"), {e.strip() for e in (m.group(2) or "").split(",") if e.strip()}


def _closure(roots: list[str]) -> set[str]:
    """Declared packages plus everything they pull in, following only the extras actually requested."""
    seen: set[str] = set()
    todo = [_parse(r) for r in roots]
    while todo:
        name, extras = todo.pop()
        key = name + "[" + ",".join(sorted(extras)) + "]"
        if key in seen:
            continue
        seen.add(key)
        try:
            reqs = requires(name) or []
        except PackageNotFoundError:
            continue
        for r in reqs:
            marker = r.split(";", 1)[1] if ";" in r else ""
            wanted = re.findall(r"extra\s*==\s*[\"']([^\"']+)", marker)
            if wanted and not set(wanted) & extras:
                continue
            todo.append(_parse(r))
    return {k.split("[")[0] for k in seen}


def test_runtime_imports_are_declared():
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text())
    allowed = _closure(meta["project"]["dependencies"])
    dists = packages_distributions()
    missing = set()
    for f in (ROOT / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top == "app" or top in sys.stdlib_module_names:
                    continue
                owners = {d.lower().replace("_", "-") for d in dists.get(top, [top])}
                if not owners & allowed:
                    missing.add(f"{top} ({f.relative_to(ROOT)})")
    assert not missing, f"imported but not in [project].dependencies: {sorted(missing)}"
