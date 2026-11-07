"""Keep the default desktop installation free of unused heavyweight components."""

import tomllib
from pathlib import Path


def runtime_dependencies():
    lock = tomllib.loads((Path(__file__).parents[1] / "uv.lock").read_text())
    packages = {package["name"]: package for package in lock["package"]}
    found = set()

    def visit(name):
        if name in found:
            return
        found.add(name)
        for dependency in packages[name].get("dependencies", []):
            visit(dependency["name"])

    visit("studio-buddy")
    return found


def test_desktop_does_not_install_unused_qt_components():
    assert runtime_dependencies().isdisjoint({"pyside6-addons", "pyside6-webengine", "pyside6-pdf"})


def test_default_install_does_not_include_mcp_server_stack():
    assert runtime_dependencies().isdisjoint(
        {"mcp", "starlette", "uvicorn", "python-multipart"}
    )


def test_desktop_starts_and_explains_missing_mcp_extra():
    import os
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import asyncio
import importlib.abc
import sys

class NoMCP(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mcp" or fullname.startswith("mcp."):
            raise ModuleNotFoundError("MCP intentionally unavailable", name="mcp")

sys.meta_path.insert(0, NoMCP())
from PySide6.QtWidgets import QApplication
from studiobuddy.app import Window
from studiobuddy.renoise import Renoise, ContextError
app = QApplication([])
window = Window()
window.close()
try:
    asyncio.run(Renoise().fetch())
except ContextError as error:
    assert "[renoise]" in str(error), str(error)
else:
    raise AssertionError("Missing extra must explain how to install it")
""",
        ],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
