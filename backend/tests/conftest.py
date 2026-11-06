import pytest

from trafficsim.network.demo import build_demo_network
from trafficsim.network.types import Network


@pytest.fixture(scope="session")
def net() -> Network:
    return build_demo_network()
