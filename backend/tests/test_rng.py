import numpy as np
import pytest

from trafficsim.engine.rng import STREAM_NAMES, RngStreams


def _draws(rs: RngStreams) -> dict[str, np.ndarray]:
    return {name: rs.get(name).random(1000) for name in STREAM_NAMES}


def test_same_seed_gives_identical_streams():
    a, b = _draws(RngStreams(123)), _draws(RngStreams(123))
    for name in STREAM_NAMES:
        np.testing.assert_array_equal(a[name], b[name])


def test_different_seeds_differ():
    a, b = _draws(RngStreams(1)), _draws(RngStreams(2))
    for name in STREAM_NAMES:
        assert not np.array_equal(a[name], b[name])


def test_streams_are_mutually_distinct():
    d = _draws(RngStreams(7))
    names = list(STREAM_NAMES)
    for i, n1 in enumerate(names):
        for n2 in names[i + 1 :]:
            assert not np.array_equal(d[n1], d[n2])


def test_streams_are_isolated_from_each_other():
    """Extra draws in one subsystem must not shift any other subsystem's numbers."""
    ref = RngStreams(99)
    perturbed = RngStreams(99)
    perturbed.route.random(12345)  # e.g. route-choice code starts drawing more numbers
    np.testing.assert_array_equal(ref.spawn.random(500), perturbed.spawn.random(500))
    np.testing.assert_array_equal(ref.behaviour.random(500), perturbed.behaviour.random(500))


def test_known_first_values_are_pinned():
    """Pin actual numbers: catches any change of bit generator, seeding or stream order
    (e.g. a NumPy upgrade or someone inserting a stream name in the middle)."""
    rs = RngStreams(2026)
    first = [int(rs.get(n).integers(0, 2**31)) for n in STREAM_NAMES]
    assert first == [1350858066, 1608267579, 190381439, 1000574433]


def test_fingerprint_tracks_state():
    a, b = RngStreams(5), RngStreams(5)
    assert a.state_fingerprint() == b.state_fingerprint()
    a.spawn.random()
    assert a.state_fingerprint() != b.state_fingerprint()


@pytest.mark.parametrize("bad", [-1, 1.5, "3", True, None])
def test_rejects_invalid_seeds(bad):
    with pytest.raises(ValueError):
        RngStreams(bad)


def test_unknown_stream_name():
    with pytest.raises(KeyError):
        RngStreams(0).get("weather")
