"""Serpentine / channel layout helpers for Primus grids."""

from __future__ import annotations


def serpentine_pixel_order(cols: int, rows: int) -> list[int]:
    """
    Map progressive (row-major) pixel index -> serpentine wire index.

    Odd rows are reversed (matches PrimusV3 V4 apply_serpentine).
    """
    order = []
    for r in range(rows):
        row_indices = list(range(r * cols, (r + 1) * cols))
        if r % 2 == 1:
            row_indices = row_indices[::-1]
        order.extend(row_indices)
    return order


def progressive_from_serpentine(cols: int, rows: int) -> list[int]:
    """Inverse map: wire index -> progressive index (for Reorder CHOP source)."""
    forward = serpentine_pixel_order(cols, rows)
    inverse = [0] * len(forward)
    for progressive_i, wire_i in enumerate(forward):
        inverse[wire_i] = progressive_i
    return inverse


def rgb_channel_names(pixel_count: int) -> list[str]:
    """DMX-style channel names for pixel_count RGB pixels: r0 g0 b0 r1 ..."""
    names = []
    for i in range(pixel_count):
        names.extend([f"r{i}", f"g{i}", f"b{i}"])
    return names


def serpentine_rgb_reorder_indices(cols: int, rows: int) -> list[int]:
    """
    For a CHOP with channels ordered progressive RGB (r0,g0,b0,r1,...),
    return channel indices in serpentine RGB order for a Select/Reorder CHOP.
    """
    # TOP->CHOP is progressive. ArtDmx needs wire (serpentine) order.
    inverse = progressive_from_serpentine(cols, rows)
    indices = []
    for wire_px in range(cols * rows):
        prog = inverse[wire_px]
        base = prog * 3
        indices.extend([base, base + 1, base + 2])
    return indices
