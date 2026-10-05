"""Exercise the real Home Assistant integration, not a mocked package namespace."""
import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield
