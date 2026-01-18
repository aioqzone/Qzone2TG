import pytest


@pytest.fixture(autouse=True, scope="session")
def debug_threads():
    yield
    import qzemoji

    qzemoji.close()
