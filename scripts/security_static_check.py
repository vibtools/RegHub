from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (ROOT / "app", ROOT / "scripts")
_SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{32,}\b"),
)


def qualified_name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def inspect_python(path: Path) -> list[str]:
    findings: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = qualified_name(node.func)
        if name in {"eval", "exec", "os.system"}:
            findings.append(f"{path.relative_to(ROOT)}:{node.lineno}: banned call {name}")
        if name.startswith("subprocess."):
            for keyword in node.keywords:
                if (
                    keyword.arg == "shell"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    findings.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: subprocess shell=True"
                    )
        if name.endswith(("Client", "request", "get", "post")):
            for keyword in node.keywords:
                if (
                    keyword.arg == "verify"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False
                ):
                    findings.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: TLS verification disabled"
                    )
    return findings


def main() -> int:
    findings: list[str] = []
    for source_root in SOURCE_ROOTS:
        for path in sorted(source_root.rglob("*.py")):
            if "__pycache__" not in path.parts:
                findings.extend(inspect_python(path))
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts or path.stat().st_size > 5_000_000:
            continue
        data = path.read_bytes()
        if b"\x00" in data[:8192]:
            continue
        if any(pattern.search(data) for pattern in _SECRET_PATTERNS):
            findings.append(f"{path.relative_to(ROOT)}: high-confidence credential signature")
    if findings:
        raise RuntimeError("Static security validation failed:\n" + "\n".join(findings))
    print("Static security validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
