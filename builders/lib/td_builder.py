"""
TouchDesigner network builder helpers.

Imported modules do not see Textport/DAT builtins (`op`, `baseCOMP`, ...).
Call `prepare_build(globals())` at the start of every `build()` so those
symbols are bound for both this package and the calling builder module.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

_TD: dict = {}

# Reload order: leaf helpers first, then package. Do not reload run_phase here -
# it may be mid-call when refresh_td_builder() invokes this.
_RELOAD_ORDER = (
    "builders.lib.output_types",
    "builders.lib.packets",
    "builders.lib.serpentine",
    "builders.lib.td_builder",
    "builders.lib",
)


def ensure_repo_on_path(root=None) -> str:
    """Put the tdprimus repo root on sys.path (project.folder inside TD)."""
    if root is None:
        try:
            root = project.folder  # noqa: F821 - TD
        except Exception:
            root = str(Path(__file__).resolve().parents[2])
    root = str(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def reload_builders(extra_modules=None):
    """
    Force-reload builders.lib.* so Textport / stale sys.modules pick up disk edits.

    Purges cached lib (and phase) modules then re-imports. Does not drop
    ``builders.run_phase`` so callers mid-``load_phase`` stay valid.

    Returns the fresh ``builders.lib.td_builder`` module.
    """
    ensure_repo_on_path()
    importlib.invalidate_caches()
    names = list(_RELOAD_ORDER)
    if extra_modules:
        for m in extra_modules:
            if m not in names:
                names.append(m)
    # Drop lib + phase caches; keep builders.run_phase if it is mid-call.
    for key in list(sys.modules):
        if key.startswith("builders.phase"):
            del sys.modules[key]
        elif key == "builders.lib" or key.startswith("builders.lib."):
            del sys.modules[key]
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            print(f"[primus] reload {name}: {exc}")
    return sys.modules["builders.lib.td_builder"]

_TD_NAMES = (
    "op",
    "me",
    "project",
    "root",
    "tdu",
    "baseCOMP",
    "containerCOMP",
    "tableDAT",
    "textDAT",
    "executeDAT",
    "scriptTOP",
    "constantTOP",
    "resolutionTOP",
    "transformTOP",
    "switchTOP",
    "crossTOP",
    "topToCHOP",
    "dattoCHOP",
    "shuffleCHOP",
    "reorderCHOP",
    "renameCHOP",
    "selectCHOP",
    "mergeCHOP",
    "switchCHOP",
    "patternCHOP",
    "constantCHOP",
    "dmxoutCHOP",
    "timerCHOP",
    "udpinDAT",
    "udpoutDAT",
    "parexecDAT",
    "chopexecDAT",
    "datexecDAT",
)


def in_touchdesigner() -> bool:
    try:
        import td  # noqa: F401

        return True
    except ImportError:
        return False


def require_td():
    if not in_touchdesigner():
        raise RuntimeError(
            "This builder must run inside TouchDesigner "
            "(use PrimusControl panel, or Textport)."
        )


def bind_td(namespace=None) -> dict:
    """Capture TD builtins from caller / __main__ / td module."""
    sources = []
    if namespace:
        sources.append(namespace)

    frame = inspect.currentframe()
    try:
        f = frame.f_back
        depth = 0
        while f is not None and depth < 12:
            g = f.f_globals
            if "op" in g and callable(g["op"]):
                sources.append(g)
                break
            f = f.f_back
            depth += 1
    finally:
        del frame

    try:
        import __main__

        sources.append(vars(__main__))
    except Exception:
        pass

    try:
        import td

        sources.append(vars(td))
        if hasattr(td, "op"):
            _TD["op"] = td.op
    except Exception:
        pass

    for src in sources:
        for name in _TD_NAMES:
            if name in _TD:
                continue
            if name in src:
                _TD[name] = src[name]
    return _TD


def inject_td_symbols(target) -> None:
    """Copy bound TD symbols onto a module, dict, or object."""
    bind_td(target if isinstance(target, dict) else None)
    if isinstance(target, dict):
        for name, value in _TD.items():
            target[name] = value
        return
    for name, value in _TD.items():
        setattr(target, name, value)


def prepare_build(module_globals=None) -> dict:
    """
    Call at the top of every builder `build()`.

    Example:
        def build(...):
            prepare_build(globals())
    """
    require_td()
    if module_globals is None:
        module_globals = inspect.currentframe().f_back.f_globals
    bind_td(module_globals)
    inject_td_symbols(module_globals)
    # Also expose on this module so ensure_base / create_child work
    inject_td_symbols(sys.modules[__name__])
    if "op" not in _TD:
        raise RuntimeError(
            "TouchDesigner op() not found. Run via PrimusControl or Textport "
            "inside a .toe saved in the tdprimus repo."
        )
    return _TD


def td_op(path: str):
    if "op" not in _TD:
        bind_td()
    return _TD["op"](path)


def td_type(name: str):
    if name not in _TD:
        bind_td()
    if name not in _TD:
        # Late lookup: TD may expose OP classes on the td module
        try:
            import td

            obj = getattr(td, name, None)
            if obj is not None:
                _TD[name] = obj
        except Exception:
            pass
    if name not in _TD:
        raise NameError(
            f"TouchDesigner type {name!r} not bound. Call prepare_build(globals()) first."
        )
    return _TD[name]


def create_child(parent, type_name: str, name: str):
    """parent.create(SomeOP, name) without needing SomeOP in scope."""
    return parent.create(td_type(type_name), name)


def ensure_base(path: str, name: str, *, recreate: bool = False):
    """Create or return a Base COMP at parent path.

    If recreate=True, destroy any existing COMP with that name first.
    """
    if "op" not in _TD:
        prepare_build()
    parent = td_op(path)
    if parent is None:
        raise ValueError(f"parent op not found: {path}")
    existing = parent.op(name)
    if existing is not None:
        if recreate:
            try:
                existing.destroy()
            except Exception as exc:  # noqa: BLE001
                print(f"[primus builder] warn: destroy {path}/{name}: {exc}")
            existing = parent.op(name)
        if existing is not None and not recreate:
            return existing
    return create_child(parent, "baseCOMP", name)


def clear_children(container, keep_names=None):
    """Destroy child ops except those in keep_names (safe for TD invalidation)."""
    keep = set(keep_names or [])
    # Snapshot names first - destroying one child can invalidate sibling refs.
    try:
        names = [c.name for c in list(container.children)]
    except Exception as exc:  # noqa: BLE001
        print(f"[primus builder] warn: list children: {exc}")
        return
    for name in names:
        if name in keep:
            continue
        child = container.op(name)
        if child is None:
            continue
        try:
            child.destroy()
        except Exception as exc:  # noqa: BLE001
            print(f"[primus builder] warn: destroy {name}: {exc}")


def place(node, x: int, y: int):
    node.nodeX = x
    node.nodeY = y
    return node


def connect(src, dst, dst_input=0):
    """Connect src output 0 to dst input index."""
    dst.inputConnectors[dst_input].connect(src)
    return dst


def set_par(node, **kwargs):
    """Set parameters by name; skips missing pars quietly with warning print."""
    for key, value in kwargs.items():
        par = getattr(node.par, key, None)
        if par is None:
            par = getattr(node.par, key.lower(), None)
        if par is None:
            print(f"[primus builder] warn: {node.path} has no par '{key}'")
            continue
        try:
            par.val = value
        except Exception as exc:  # noqa: BLE001
            print(f"[primus builder] warn: set {node.path}.par.{key}: {exc}")
    return node


DEVICE_TABLE_COLS = [
    "name",
    "ip",
    "universe",
    "recv_mode",
    "a0_type",
    "a0_count",
    "a0_virtual",
    "a1_type",
    "a1_count",
    "a1_virtual",
    "group",
]


def init_device_table(table_dat, rows=None):
    """Initialize a Table DAT with device schema and optional data rows."""
    table_dat.clear()
    table_dat.appendRow(DEVICE_TABLE_COLS)
    for row in rows or []:
        table_dat.appendRow([str(row.get(c, "")) for c in DEVICE_TABLE_COLS])
    return table_dat


CUE_TABLE_COLS = [
    "cue",
    "targets",
    "a0_content",
    "a1_content",
    "brightness",
    "hue_shift",
    "blackout",
    "fade",
    "notes",
]


def init_cue_table(table_dat, rows=None):
    table_dat.clear()
    table_dat.appendRow(CUE_TABLE_COLS)
    for row in rows or []:
        table_dat.appendRow([str(row.get(c, "")) for c in CUE_TABLE_COLS])
    return table_dat
