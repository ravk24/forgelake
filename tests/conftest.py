import pytest


@pytest.fixture(scope="session")
def spark():
    """One shared local Spark session for every `spark`-marked test (startup is slow)."""
    from forgelake.utils.spark import get_spark

    session = get_spark(app_name="forgelake-tests")
    yield session
    session.stop()
