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
    assert runtime_dependencies().isdisjoint(
        {"pyside6-addons", "pyside6-webengine", "pyside6-pdf"}
    )
