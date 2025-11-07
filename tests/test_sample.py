import pytest


def test_add():
    assert 1 + 1 == 2


def test_upper():
    assert "chatstack".upper() == "CHATSTACK"


@pytest.mark.skip(reason="demo skip")
def test_skipped():
    assert True
