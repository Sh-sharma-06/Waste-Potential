"""Test-side helper: tests pass an explicit methane fraction.

Production code has no default for ch4_fraction. These wrappers supply a test
constant so the existing tests stay readable. Not used by any route.
"""

import app.ml.yield_model.predict as _predict

TEST_CH4_FRACTION = 0.60


def estimate(*args, **kwargs):
    kwargs.setdefault("ch4_fraction", TEST_CH4_FRACTION)
    return _predict.estimate(*args, **kwargs)


def estimate_illustrative_l1(*args, **kwargs):
    kwargs.setdefault("ch4_fraction", TEST_CH4_FRACTION)
    return _predict.estimate_illustrative_l1(*args, **kwargs)