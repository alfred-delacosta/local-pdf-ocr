# Copyright Advanced Software and AI Solutions LLC
"""Task runner: python tasks.py <dev|start|test|lint|build>."""

from __future__ import annotations

import compileall
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DASH_RE = re.compile("[\u2013\u2014]")  # en dash, em dash
STATIC_REF_RE = re.compile(
    r"""(?:href|src)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)


def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=ROOT)
    return int(completed.returncode)


def load_env_for_uvicorn() -> tuple[str, str]:
    host = "127.0.0.1"
    port = "3000"
    env_path = ROOT / ".env"
    if env_path.is_file():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key == "HOST" and value:
                host = value
            if key == "PORT" and value:
                port = value
    import os

    host = os.environ.get("HOST", host) or host
    port = os.environ.get("PORT", port) or port
    return host, str(port)


def lint_copy() -> int:
    bad: list[str] = []
    roots = [
        ROOT / "app",
        ROOT / "static",
        ROOT / "tests",
        ROOT / "docs",
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        ROOT / "tasks.py",
        ROOT / ".env.example",
    ]
    files: list[Path] = []
    for item in roots:
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            for path in item.rglob("*"):
                if path.is_file() and path.suffix.lower() in {
                    ".py",
                    ".md",
                    ".html",
                    ".css",
                    ".js",
                    ".txt",
                    ".example",
                }:
                    files.append(path)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if DASH_RE.search(text):
            bad.append(str(path.relative_to(ROOT)))
    if bad:
        print("lint:copy failed; em/en dashes found in:")
        for item in bad:
            print(" ", item)
        return 1
    print("lint:copy ok")
    return 0


def check_static_refs() -> int:
    index = ROOT / "static" / "index.html"
    if not index.is_file():
        print("missing static/index.html")
        return 1
    html = index.read_text(encoding="utf-8")
    missing: list[str] = []
    for ref in STATIC_REF_RE.findall(html):
        if ref.startswith("http://") or ref.startswith("https://") or ref.startswith("#"):
            continue
        if ref.startswith("/static/"):
            rel = ref[len("/static/") :]
            path = ROOT / "static" / rel
        elif ref.startswith("/"):
            path = ROOT / ref.lstrip("/")
        else:
            path = ROOT / "static" / ref
        if not path.is_file():
            missing.append(ref)
    if missing:
        print("build: missing static files referenced by index.html:")
        for item in missing:
            print(" ", item)
        return 1
    print("static refs ok")
    return 0


def cmd_lint() -> int:
    code = run([sys.executable, "-m", "ruff", "check", "app", "tests", "tasks.py"])
    if code:
        return code
    code = run([sys.executable, "-m", "ruff", "format", "--check", "app", "tests", "tasks.py"])
    if code:
        return code
    return lint_copy()


def cmd_test() -> int:
    return run([sys.executable, "-m", "pytest", "-q"])


def cmd_build() -> int:
    code = cmd_lint()
    if code:
        return code
    code = cmd_test()
    if code:
        return code
    if not compileall.compile_dir(str(ROOT / "app"), quiet=1):
        print("compileall failed")
        return 1
    return check_static_refs()


def cmd_dev() -> int:
    host, port = load_env_for_uvicorn()
    return run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            host,
            "--port",
            port,
        ]
    )


def cmd_start() -> int:
    host, port = load_env_for_uvicorn()
    return run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            port,
        ]
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in {"dev", "start", "test", "lint", "build"}:
        print("Usage: python tasks.py <dev|start|test|lint|build>")
        return 2
    name = argv[1]
    if name == "dev":
        return cmd_dev()
    if name == "start":
        return cmd_start()
    if name == "test":
        return cmd_test()
    if name == "lint":
        return cmd_lint()
    if name == "build":
        return cmd_build()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
