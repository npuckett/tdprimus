"""builders.lib package - PrimusV3 TD helpers."""

from .output_types import (
    COMBINED_RECEIVE_MAX_PIXELS,
    LOOK_OUTPUT_TYPES,
    OUTPUT_TYPES,
    TYPE_TO_ID,
    default_virtual,
    layout_of,
    physical_pixels,
    resize_dims_for,
    validate_combined,
)
from .packets import (
    ARTNET_PORT,
    build_art_address,
    build_art_dmx,
    build_art_poll,
    build_ip_config,
    build_output_config,
    build_receive_config,
    build_virtual_resolution,
    bytes_to_td_hex,
    parse_art_poll_reply,
    parse_pv3cap1,
)
from .serpentine import (
    rgb_channel_names,
    serpentine_pixel_order,
    serpentine_rgb_reorder_indices,
)

__all__ = [
    "ARTNET_PORT",
    "COMBINED_RECEIVE_MAX_PIXELS",
    "LOOK_OUTPUT_TYPES",
    "OUTPUT_TYPES",
    "TYPE_TO_ID",
    "build_art_address",
    "build_art_dmx",
    "build_art_poll",
    "build_ip_config",
    "build_output_config",
    "build_receive_config",
    "build_virtual_resolution",
    "bytes_to_td_hex",
    "default_virtual",
    "layout_of",
    "parse_art_poll_reply",
    "parse_pv3cap1",
    "physical_pixels",
    "resize_dims_for",
    "rgb_channel_names",
    "serpentine_pixel_order",
    "serpentine_rgb_reorder_indices",
    "validate_combined",
]
