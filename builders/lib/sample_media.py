"""
Media sampling helpers for Primus ArtDmx packaging.

Given an image as HxWxC float array (0-1 or 0-255) and a virtual pixel count,
sample N RGB triplets according to a geometric mode.

Modes
-----
fit       - map N samples across a target W×H; optional non-default ROI narrows it
hline     - N samples along a horizontal line at normalized v
vline     - N samples along a vertical line at normalized u
line      - N samples along segment (u,v) -> (u1,v1)
point     - every sample is the color at (u,v)  [flood / virt=1 pick]
roi_fit   - same as fit but restricted to roi (u,v,w,h) in 0-1
"""

from __future__ import annotations

from typing import Iterable


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else float(x)


def _as_unit_rgb(pix, as_byte: bool, level: int) -> tuple[int, int, int]:
    level = max(0, min(255, int(level)))
    scale = level / 255.0
    if as_byte:
        r = int(max(0, min(255, float(pix[0]) * scale)))
        g = int(max(0, min(255, float(pix[1]) * scale)))
        b = int(max(0, min(255, float(pix[2]) * scale)))
    else:
        r = int(max(0, min(255, float(pix[0]) * 255.0 * scale)))
        g = int(max(0, min(255, float(pix[1]) * 255.0 * scale)))
        b = int(max(0, min(255, float(pix[2]) * 255.0 * scale)))
    return r, g, b


def _peak_is_byte(arr) -> bool:
    try:
        return float(arr[:, :, :3].max()) > 1.5
    except Exception:
        return False


def _sample_uv(arr, u: float, v: float):
    """Nearest-neighbour sample; arr is HxWxC; u/v in 0-1."""
    h, w = int(arr.shape[0]), int(arr.shape[1])
    if h < 1 or w < 1:
        return None
    xi = int(_clamp01(u) * (w - 1) + 0.5) if w > 1 else 0
    yi = int(_clamp01(v) * (h - 1) + 0.5) if h > 1 else 0
    xi = max(0, min(w - 1, xi))
    yi = max(0, min(h - 1, yi))
    return arr[yi, xi]


def sample_media_rgb(
    arr,
    n: int,
    mode: str = "hline",
    *,
    u: float = 0.0,
    v: float = 0.5,
    u1: float = 1.0,
    v1: float = 0.5,
    roi_u: float = 0.0,
    roi_v: float = 0.0,
    roi_w: float = 1.0,
    roi_h: float = 1.0,
    level: int = 64,
    grid_w: int | None = None,
    grid_h: int | None = None,
) -> bytes:
    """
    Return n*3 RGB bytes sampled from arr (HxWxC).

    For fit/roi_fit, grid_w/grid_h define the virtual lattice (defaults: n×1).
    """
    n = max(0, int(n))
    if n <= 0 or arr is None:
        return b""
    try:
        h = int(arr.shape[0])
        w = int(arr.shape[1])
        if h < 1 or w < 1 or int(arr.shape[2]) < 3:
            return bytes(n * 3)
    except Exception:
        return bytes(n * 3)

    mode = (mode or "hline").strip().lower()
    as_byte = _peak_is_byte(arr)
    out = bytearray()

    ru, rv = _clamp01(roi_u), _clamp01(roi_v)
    rw, rh = max(1e-6, float(roi_w)), max(1e-6, float(roi_h))
    if ru + rw > 1.0:
        rw = 1.0 - ru
    if rv + rh > 1.0:
        rh = 1.0 - rv

    def emit(uu, vv):
        pix = _sample_uv(arr, uu, vv)
        if pix is None:
            out.extend((0, 0, 0))
        else:
            out.extend(_as_unit_rgb(pix, as_byte, level))

    if mode == "point":
        for _ in range(n):
            emit(u, v)
        return bytes(out)

    def linear_t(i):
        # Include both endpoints: an n×1 sample maps cleanly across full width.
        return 0.5 if n == 1 else i / float(n - 1)

    if mode == "hline":
        vv = _clamp01(v)
        for i in range(n):
            t = linear_t(i)
            emit(ru + t * rw, rv + vv * rh)
        return bytes(out)

    if mode == "vline":
        uu = _clamp01(u)
        for i in range(n):
            t = linear_t(i)
            emit(ru + uu * rw, rv + t * rh)
        return bytes(out)

    if mode == "line":
        for i in range(n):
            t = linear_t(i)
            emit(
                _clamp01(u) + (_clamp01(u1) - _clamp01(u)) * t,
                _clamp01(v) + (_clamp01(v1) - _clamp01(v)) * t,
            )
        return bytes(out)

    # `roi_fit` explicitly uses the ROI. `fit` uses the full frame unless the
    # caller supplied a non-default ROI, which makes `fit` useful as a compact
    # override without changing modes.
    if mode in ("fit", "roi_fit"):
        if mode == "fit":
            roi_requested = (
                abs(ru) > 1e-6 or abs(rv) > 1e-6
                or abs(rw - 1.0) > 1e-6 or abs(rh - 1.0) > 1e-6
            )
            if not roi_requested:
                ru, rv, rw, rh = 0.0, 0.0, 1.0, 1.0
        gw = max(1, int(grid_w) if grid_w else n)
        gh = max(1, int(grid_h) if grid_h else 1)
        for i in range(n):
            if gh <= 1:
                # if n > gw, still march in one row across n
                uu = ru + linear_t(i) * rw
                vv = rv + 0.5 * rh
            else:
                row = i // gw
                col = i % gw
                if row >= gh:
                    out.extend((0, 0, 0))
                    continue
                uu = ru + (0.5 if gw == 1 else col / float(gw - 1)) * rw
                vv = rv + (0.5 if gh == 1 else row / float(gh - 1)) * rh
            emit(uu, vv)
        return bytes(out)

    # unknown mode -> hline fallback
    return sample_media_rgb(
        arr, n, "hline", u=u, v=v, level=level, roi_u=roi_u, roi_v=roi_v, roi_w=roi_w, roi_h=roi_h
    )


SAMPLE_MODES: Iterable[str] = (
    "fit",
    "roi_fit",
    "hline",
    "vline",
    "line",
    "point",
)
