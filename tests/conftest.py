import pytest

from app import app
from rate_limit import limiter


@pytest.fixture(autouse=True)
def disable_rate_limiting_by_default():
    app.config["RATELIMIT_ENABLED"] = False
    limiter.reset()
    yield
    app.config["RATELIMIT_ENABLED"] = False
    limiter.reset()
