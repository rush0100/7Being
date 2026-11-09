"""Device plugin catalog for Studio install UI."""

from __future__ import annotations

from sevenbeing.brain.bci.devices.catalog import (
    CATALOG,
    hack_root,
    list_plugins,
    local_path,
    plugin_by_id,
)


def test_catalog() -> None:
    assert len(CATALOG) == 3
    assert plugin_by_id("epocx") is not None
    assert plugin_by_id("7being-h1") is not None
    root = hack_root()
    assert root.is_dir()
    ep = plugin_by_id("epocx")
    assert ep is not None
    # Sibling repo should exist in this workspace
    path = local_path(ep)
    assert path is not None, f"expected local 7being-emotiv-epocx under {root}"
    status = list_plugins(["epocx"])
    assert status[0]["id"] == "epocx"
    assert status[0]["loaded"] is True


if __name__ == "__main__":
    test_catalog()
    print("ok")
