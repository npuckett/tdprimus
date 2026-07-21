"""
Load and run a phase builder inside TouchDesigner with TD builtins bound.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path


PHASE_MODULES = {
    1: "builders.phase1_baseline",
    2: "builders.phase2_combined",
    3: "builders.phase3_virtual",
    4: "builders.phase4_generative",
    5: "builders.phase5_multidevice",
    6: "builders.phase6_cues",
    7: "builders.phase7_discovery",
    8: "builders.phase8_remote_config",
    9: "builders.phase9_components",
}


def repo_root():
    try:
        return Path(project.folder)  # noqa: F821 - TD
    except Exception:
        return Path(__file__).resolve().parents[1]


def ensure_sys_path():
    root = str(repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def purge_builders_lib():
    """
    Drop cached builders.lib.* so create_child / prepare_build match disk.

    TouchDesigner keeps sys.modules across Textport exec() runs; an older
    td_builder without create_child will otherwise keep failing.
    """
    for key in list(sys.modules):
        if key == "builders.lib" or key.startswith("builders.lib."):
            del sys.modules[key]
        elif key.startswith("builders.phase"):
            del sys.modules[key]


def refresh_td_builder():
    """Import builders.lib.td_builder from disk (purge-first if stale)."""
    ensure_sys_path()
    importlib.invalidate_caches()
    name = "builders.lib.td_builder"
    cached = sys.modules.get(name)
    # Stale copy without create_child/reload_builders - must purge, not reload.
    if cached is not None and not hasattr(cached, "create_child"):
        purge_builders_lib()
        return importlib.import_module(name)
    if cached is not None and hasattr(cached, "reload_builders"):
        return cached.reload_builders()
    if cached is not None:
        # Has create_child but no reload_builders - reload in place
        return importlib.reload(cached)
    return importlib.import_module(name)


def load_phase(phase: int, td_namespace=None):
    ensure_sys_path()
    # Force disk-fresh helpers (fixes stale create_child in TD sys.modules)
    td_builder = refresh_td_builder()
    prepare_build = td_builder.prepare_build
    inject_td_symbols = td_builder.inject_td_symbols

    mod_name = PHASE_MODULES[int(phase)]
    # Fresh reload so script edits apply
    if mod_name in sys.modules:
        mod = importlib.reload(sys.modules[mod_name])
    else:
        mod = importlib.import_module(mod_name)

    # Prefer explicit TD namespace (PrimusControlExt / Bridge) so op() is bound
    if td_namespace:
        prepare_build(td_namespace)
        inject_td_symbols(td_namespace)
    prepare_build(vars(mod))
    inject_td_symbols(mod)
    return mod


def run_phase(phase: int, td_namespace=None, **kwargs):
    """
    Import builders.phaseN_*.build and call it with kwargs.

    Example:
        run_phase(1, device_ip='192.168.8.166', universe=0, output_type='small_grid')

    td_namespace: optional dict of TD builtins (op, baseCOMP, ...) for prepare_build.
    Stripped before calling build() so phase builders do not see it.
    """
    mod = load_phase(phase, td_namespace=td_namespace)
    if not hasattr(mod, "build"):
        raise RuntimeError(f"{PHASE_MODULES[int(phase)]} has no build()")
    print(f"[primus] running phase {phase} with {kwargs}")
    return mod.build(**kwargs)


def settings_from_table(table) -> dict:
    """Read PrimusControl settings table (param/value rows) into a dict."""
    out = {}
    for r in range(1, table.numRows):
        key = table[r, 0].val.strip()
        val = table[r, 1].val.strip()
        out[key] = val
    return out


def kwargs_for_phase(phase: int, settings: dict) -> dict:
    phase = int(phase)
    # Sticky CLI kwargs (survives PrimusBridge deleting .td_cmd.json)
    sticky = {}
    try:
        from pathlib import Path
        import json

        candidates = []
        try:
            candidates.append(Path(project.folder) / "builders" / ".td_build_kwargs.json")  # noqa: F821
        except Exception:
            pass
        candidates.append(Path(__file__).resolve().parent / ".td_build_kwargs.json")
        for path in candidates:
            if path.exists():
                sticky = json.loads(path.read_text(encoding="utf-8"))
                break
    except Exception:
        sticky = {}

    merged = dict(settings)
    for key in (
        "ip",
        "device_ip",
        "universe",
        "a0_type",
        "a1_type",
        "a0_virtual",
        "a1_virtual",
        "recv_mode",
        "pattern",
        "a0_pattern",
        "a1_pattern",
        "level",
        "a0_source",
        "a1_source",
        "bind_ip",
    ):
        if sticky.get(key) is not None and sticky.get(key) != "":
            merged[key] = sticky[key]

    ip = merged.get("ip") or merged.get("device_ip") or "192.168.8.166"
    universe = int(merged.get("universe", "0") or 0)
    a0 = merged.get("a0_type", "small_grid")
    a1 = merged.get("a1_type", "long_strip")

    if phase == 1:
        kw = {"device_ip": ip, "universe": universe, "output_type": a0}
        if merged.get("pattern"):
            kw["pattern"] = str(merged["pattern"])
        if merged.get("level") is not None and merged.get("level") != "":
            kw["level"] = int(merged["level"])
        return kw
    if phase == 2:
        kw = {
            "device_ip": ip,
            "universe": universe,
            "a0_type": a0,
            "a1_type": a1,
            "recv_mode": merged.get("recv_mode") or "combined",
        }
        if merged.get("a0_virtual") is not None and merged.get("a0_virtual") != "":
            kw["a0_virtual"] = int(merged["a0_virtual"])
        if merged.get("a1_virtual") is not None and merged.get("a1_virtual") != "":
            kw["a1_virtual"] = int(merged["a1_virtual"])
        if merged.get("a0_pattern"):
            kw["a0_pattern"] = str(merged["a0_pattern"])
        if merged.get("a1_pattern"):
            kw["a1_pattern"] = str(merged["a1_pattern"])
        if merged.get("level") is not None and merged.get("level") != "":
            kw["level"] = int(merged["level"])
        return kw
    if phase == 3:
        kw = {
            "device_ip": ip,
            "universe": universe,
            "a0_type": a0,
            "a1_type": a1,
            "recv_mode": merged.get("recv_mode") or "split",
        }
        if merged.get("a0_virtual") is not None and merged.get("a0_virtual") != "":
            kw["a0_virtual"] = int(merged["a0_virtual"])
        if merged.get("a1_virtual") is not None and merged.get("a1_virtual") != "":
            kw["a1_virtual"] = int(merged["a1_virtual"])
        if merged.get("a0_pattern"):
            kw["a0_pattern"] = str(merged["a0_pattern"])
        if merged.get("a1_pattern"):
            kw["a1_pattern"] = str(merged["a1_pattern"])
        if merged.get("level") is not None and merged.get("level") != "":
            kw["level"] = int(merged["level"])
        return kw
    if phase == 4:
        kw = {
            "device_ip": ip,
            "universe": universe,
            "a0_type": a0,
            "a1_type": a1,
            "recv_mode": merged.get("recv_mode") or "split",
        }
        if merged.get("a0_virtual") is not None and merged.get("a0_virtual") != "":
            kw["a0_virtual"] = int(merged["a0_virtual"])
        if merged.get("a1_virtual") is not None and merged.get("a1_virtual") != "":
            kw["a1_virtual"] = int(merged["a1_virtual"])
        if merged.get("level") is not None and merged.get("level") != "":
            kw["level"] = int(merged["level"])
        if merged.get("a0_source") is not None and merged.get("a0_source") != "":
            kw["a0_source"] = int(merged["a0_source"])
        if merged.get("a1_source") is not None and merged.get("a1_source") != "":
            kw["a1_source"] = int(merged["a1_source"])
        if merged.get("bind_ip") is not None:
            kw["bind_ip"] = str(merged["bind_ip"])
        return kw
    if phase == 5:
        # Phase 5 owns a persistent device-profile table.  A CLI JSON list is
        # an explicit replacement for its default rows, useful before TD has a
        # table to edit.  Do not pass the generic single-device settings here.
        kw = {}
        if sticky.get("device_rows_json"):
            kw["device_rows_json"] = str(sticky["device_rows_json"])
        return kw
    return {}
