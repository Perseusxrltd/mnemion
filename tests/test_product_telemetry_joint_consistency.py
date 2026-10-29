"""Valid packet framing alone cannot make impossible categorical totals useful."""

from copy import deepcopy

import pytest

from deploy.assess_telemetry_privacy import _balanced
from mnemion.product_telemetry import wire
from mnemion.product_telemetry.publication import validate
from mnemion.product_telemetry.reporting import AggregateWindow


@pytest.mark.parametrize("count,positive", [(4096, 2560), (65536, 32768)])
def test_individually_plausible_but_jointly_impossible_views_are_withheld(count, positive):
    window = AggregateWindow(2900)
    for index in range(count):
        # Every frame is syntactically valid. Concentrating on coordinate zero
        # gives all 16 categories the same estimate: 0.5 or 0 respectively.
        assert window.contribute(bytes((wire.WIRE["version"], 0, 0, int(index < positive))))
    result = window.seal()
    validate(result)
    view = result["views"][0]
    assert view["state"] == "inconsistent_reports"
    assert view["estimates"] is None
    assert view["report_range"]["minimum"] == count
    assert window._total == 0 and not any(window._counts)
    assert all(not any(sums) for sums in window._sums)


@pytest.mark.parametrize("fraction,interval", [(0.5, [0.4, 0.6]), (0.02, [0.01, 0.04])])
def test_publisher_refuses_intervals_that_cannot_describe_one_categorical_distribution(
    fraction, interval
):
    window = AggregateWindow(2900)
    _balanced(window, 0, 1, 4096)
    original = window.seal()
    validate(original)
    forged = deepcopy(original)
    for cell in forged["views"][0]["estimates"]:
        cell.update(state="estimated", fraction=fraction, interval=interval.copy())
    # Every field is individually valid. The lower bounds sum to 6.4, or the
    # upper bounds to 0.64, while these categories must total exactly one.
    with pytest.raises(wire.WireError, match="^telemetry_invalid_report$"):
        validate(forged)
    assert validate(original) == original


def test_publisher_leaves_withheld_cells_unknown_when_visible_intervals_are_compatible():
    window = AggregateWindow(2900)
    _balanced(window, 0, 1, 4096)
    result = window.seal()
    cells = result["views"][0]["estimates"]
    cells[1].update(fraction=0.5, interval=[0.4, 0.6])
    before = deepcopy(result)
    assert validate(result) == before
    assert all(
        cell["fraction"] is None and cell["interval"] is None
        for index, cell in enumerate(cells)
        if index != 1
    )
