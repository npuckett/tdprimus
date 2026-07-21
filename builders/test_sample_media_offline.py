"""Offline checks for the Phase 4 media sampler (no TouchDesigner needed)."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from builders.lib.sample_media import sample_media_rgb  # noqa: E402


def rgb_triplets(payload):
    return [tuple(payload[i:i + 3]) for i in range(0, len(payload), 3)]


def test_hline_maps_left_to_right():
    # Four red pixels increase left-to-right. Level 255 preserves byte values.
    arr = np.zeros((2, 4, 3), dtype=np.uint8)
    arr[:, :, 0] = [0, 85, 170, 255]
    got = rgb_triplets(sample_media_rgb(arr, 4, "hline", v=.5, level=255))
    assert [pixel[0] for pixel in got] == [0, 85, 170, 255], got


def test_point_repeats_requested_pixel():
    arr = np.zeros((3, 3, 3), dtype=np.uint8)
    arr[1, 2] = [12, 34, 56]
    got = rgb_triplets(sample_media_rgb(arr, 3, "point", u=1, v=.5, level=255))
    assert got == [(12, 34, 56)] * 3, got


def test_line_has_requested_count_and_endpoints():
    arr = np.zeros((3, 3, 3), dtype=np.uint8)
    arr[0, 0] = [10, 0, 0]
    arr[2, 2] = [0, 20, 0]
    got = rgb_triplets(sample_media_rgb(arr, 3, "line", u=0, v=0, u1=1, v1=1, level=255))
    assert len(got) == 3, got
    assert got[0] == (10, 0, 0) and got[-1] == (0, 20, 0), got


if __name__ == "__main__":
    test_hline_maps_left_to_right()
    test_point_repeats_requested_pixel()
    test_line_has_requested_count_and_endpoints()
    print("sample_media offline tests: OK")
