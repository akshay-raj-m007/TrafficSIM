"""Streaming cost: frame size is exactly 12 + 13 n bytes; encoding is cheap and compresses."""

import pytest

from tools.measure_stream import bandwidth, measure
from trafficsim.server.frames import BYTES_PER_VEHICLE, HEADER

pytestmark = pytest.mark.slow  # runs a loaded simulation


def test_frame_size_bandwidth_and_cost_at_a_loaded_state():
    row = measure(1.0, warm_s=200.0, frames=40, signal="uncontrolled")
    n = row["vehicles"]
    b = bandwidth(row)
    print(f"\n[stream] {n:.0f} vehicles: raw {row['raw_B']:.0f} B/frame, deflated "
          f"{row['packed_B']:.0f} B; {b['raw_B']['KB_per_s']:.1f} KB/s raw, "
          f"{b['packed_B']['KB_per_s']:.1f} KB/s deflated; step {row['step_ms']:.2f} ms, "
          f"encode {row['encode_ms']:.3f} ms, kpi {row['kpi_ms']:.2f} ms")  # fmt: skip
    assert n > 100
    assert row["raw_B"] == pytest.approx(HEADER.size + BYTES_PER_VEHICLE * n, abs=BYTES_PER_VEHICLE)
    assert row["packed_B"] < row["raw_B"]  # structure-of-arrays frames deflate
    assert row["encode_ms"] < 20.0 and row["kpi_ms"] < 50.0
