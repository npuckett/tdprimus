"""PrimusV3 output type table - mirrors V4 config.h / state.py LOOK_OUTPUT_TYPES."""

OUTPUT_TYPES = {
    "none": {
        "id": 0,
        "pixels": 0,
        "layout": "none",
        "grid_size": None,
        "default_virtual": 0,
    },
    "short_strip": {
        "id": 1,
        "pixels": 30,
        "layout": "linear",
        "grid_size": None,
        "default_virtual": 30,
    },
    "long_strip": {
        "id": 2,
        "pixels": 72,
        "layout": "linear",
        "grid_size": None,
        "default_virtual": 72,
    },
    "grid": {
        "id": 3,
        "pixels": 64,
        "layout": "grid",
        "grid_size": (8, 8),
        "default_virtual": 64,
    },
    "small_grid": {
        "id": 4,
        "pixels": 32,
        "layout": "grid",
        "grid_size": (8, 4),
        "default_virtual": 1,  # intentional solid-color default
    },
    "extra_long_strip": {
        "id": 5,
        "pixels": 122,
        "layout": "linear",
        "grid_size": None,
        "default_virtual": 122,
    },
}

LOOK_OUTPUT_TYPES = [
    "none",
    "short_strip",
    "long_strip",
    "grid",
    "small_grid",
    "extra_long_strip",
]

TYPE_TO_ID = {name: i for i, name in enumerate(LOOK_OUTPUT_TYPES)}
COMBINED_RECEIVE_MAX_PIXELS = 170
ARTNET_PORT = 6454


def physical_pixels(type_key):
    return OUTPUT_TYPES[type_key]["pixels"]


def default_virtual(type_key):
    return OUTPUT_TYPES[type_key]["default_virtual"]


def layout_of(type_key):
    return OUTPUT_TYPES[type_key]["layout"]


def grid_size(type_key):
    return OUTPUT_TYPES[type_key]["grid_size"]


def validate_combined(virtual_a0, virtual_a1):
    """Return (ok: bool, total: int, message: str)."""
    total = int(virtual_a0) + int(virtual_a1)
    if total > COMBINED_RECEIVE_MAX_PIXELS:
        return (
            False,
            total,
            f"combined mode needs ?{COMBINED_RECEIVE_MAX_PIXELS} virtual px; got {total}",
        )
    return True, total, "ok"


def resize_dims_for(type_key, virtual_count=None):
    """
    Return (width, height) for a Resize TOP that produces `virtual_count` pixels.

    Linear:  width=virtual, height=1
    Grid:    width=cols, height=ceil(virtual/cols) when virtual < physical,
             else full grid_size. For virtual=1 on small_grid -> 1x1.
    """
    info = OUTPUT_TYPES[type_key]
    if info["layout"] == "none":
        return (1, 1)
    v = info["default_virtual"] if virtual_count is None else int(virtual_count)
    v = max(0, v)
    if info["layout"] == "linear":
        return (max(1, v), 1)
    cols, rows = info["grid_size"]
    if v <= 1:
        return (1, 1)
    if v >= info["pixels"]:
        return (cols, rows)
    # Approximate a sub-grid: keep cols, shrink rows
    h = max(1, (v + cols - 1) // cols)
    return (cols, h)
