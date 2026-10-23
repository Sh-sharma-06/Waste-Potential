import pytest

from app.ml.yield_model.feedstocks import (
    normalise_feedstock,
    MissingFeedstockError,
    UnknownFeedstockError,
    FEEDSTOCK_NAMES,
)

@pytest.mark.parametrize(
    "input_label,expected",
    [
        ("Food", "food"),
        (" food ", "food"),
    ],
)
def test_normalise_feedstock_valid(input_label, expected):
    assert normalise_feedstock(input_label) == expected

@pytest.mark.parametrize(
    "bad_input",
    [None, 5, "", "   "],
)
def test_normalise_feedstock_missing(bad_input):
    with pytest.raises(MissingFeedstockError):
        normalise_feedstock(bad_input)


