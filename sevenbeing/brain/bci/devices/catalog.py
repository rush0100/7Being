"""Known device plugins — install / status for Studio no-code UI."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PluginSpec:
    id: str
    title: str
    dist: str
    module: str
    folder: str
    serve: str
    default_port: int
    blurb: str


CATALOG: tuple[PluginSpec, ...] = (
    PluginSpec(
        id="epocx",
        title="Emotiv EPOC X",
        dist="7being-emotiv-epocx",
        module="sevenbeing_epocx",
        folder="7being-emotiv-epocx",
        serve="7being-emotiv-epocx-serve",
        default_port=51051,
        blurb="LSL adapter · ซื้อ EmotivPRO แล้วติดต่อ hello@rush0100.com · gRPC :51051",
    ),
    PluginSpec(
        id="h1",
        title="H1",
        dist="7being-h1",
        module="sevenbeing_h1",
        folder="7being-h1",
        serve="7being-h1-serve",
        default_port=51052,
        blurb="H1 1-ch EEG/EMG · UART/BLE · gRPC :51052",
    ),
    PluginSpec(
        id="ads1299",
        title="ADS1299",
        dist="7being-ads1299",
        module="sevenbeing_ads1299",
        folder="7being-ads1299",
        serve="7being-ads1299-serve",
        default_port=51053,
        blurb="ADS1299EEG-FE on MMB0 · gRPC :51053",
    ),
)


def plugin_by_id(plugin_id: str) -> PluginSpec | None:
    key = (plugin_id or "").strip().lower()
    for spec in CATALOG:
        if spec.id == key or spec.dist == key or spec.module == key:
            return spec
    return None


def hack_root() -> Path:
    """Workspace root that contains sibling ``7being-*`` folders."""
    env = os.environ.get("SEVENBEING_HACK_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    # …/7Being/sevenbeing/brain/bci/devices/catalog.py → Hack/
    here = Path(__file__).resolve()
    for parent in here.parents:
        if any((parent / name).is_dir() for name in ("7being-emotiv-epocx", "7being-h1", "7being-ads1299")):
            return parent
    # Editable install: package lives under 7Being/
    if len(here.parents) >= 5 and here.parents[4].name == "7Being":
        return here.parents[5]
    return Path.cwd()


def local_path(spec: PluginSpec) -> Path | None:
    root = hack_root()
    path = root / spec.folder
    if path.is_dir() and (path / "pyproject.toml").is_file():
        return path
    return None


def is_installed(spec: PluginSpec) -> bool:
    return importlib.util.find_spec(spec.module) is not None


def plugin_status(spec: PluginSpec, loaded_kinds: list[str] | None = None) -> dict:
    loaded = set(loaded_kinds or [])
    path = local_path(spec)
    return {
        "id": spec.id,
        "title": spec.title,
        "dist": spec.dist,
        "module": spec.module,
        "serve": spec.serve,
        "default_port": spec.default_port,
        "endpoint": f"127.0.0.1:{spec.default_port}",
        "blurb": spec.blurb,
        "installed": is_installed(spec),
        "loaded": spec.id in loaded,
        "local_path": None if path is None else str(path),
        "installable": path is not None or True,
    }


def list_plugins(loaded_kinds: list[str] | None = None) -> list[dict]:
    return [plugin_status(spec, loaded_kinds) for spec in CATALOG]


def install_plugin(plugin_id: str, *, editable: bool = True) -> dict:
    """``pip install -e`` local sibling package, else ``pip install <dist>``."""
    spec = plugin_by_id(plugin_id)
    if spec is None:
        raise KeyError(f"unknown plugin: {plugin_id}")
    path = local_path(spec)
    cmd = [sys.executable, "-m", "pip", "install"]
    if path is not None and editable:
        cmd += ["-e", str(path)]
        source = f"editable:{path}"
    else:
        cmd.append(spec.dist)
        source = f"pip:{spec.dist}"
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    ok = proc.returncode == 0 and is_installed(spec)
    return {
        "ok": ok,
        "id": spec.id,
        "source": source,
        "installed": is_installed(spec),
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-4000:],
        "serve": f"{spec.serve} --port {spec.default_port}",
        "endpoint": f"127.0.0.1:{spec.default_port}",
    }
