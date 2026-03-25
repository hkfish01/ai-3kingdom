from app.rules import compute_power, prosperity


def test_compute_power():
    assert compute_power(10, 10, 10) == 43.0


def test_prosperity():
    assert round(prosperity(0), 6) == 0
    assert prosperity(10) > prosperity(1)
