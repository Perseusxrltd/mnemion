"""Real-time review limits must survive process transfer without renewing age."""

import copy

import pytest

from mnemion.product_telemetry.review_clock import (
    REVIEW_LIFETIME_MS,
    check_review_lifetime,
    review_lifetime,
    start_review_lifetime,
)

EPOCH = "1234567890abcdef1234567890abcdef"
WALL = 10000000
CLOCK = {"epoch": EPOCH, "elapsed_ms": 50000}


def test_review_is_limited_by_both_elapsed_time_and_the_input_window():
    initial = start_review_lifetime(WALL, CLOCK, WALL + 120000)
    assert initial["expires_ms"] == WALL + 120000
    assert check_review_lifetime(initial, WALL + 119999, {**CLOCK, "elapsed_ms": 169999})
    assert check_review_lifetime(initial, WALL + 120000, {**CLOCK, "elapsed_ms": 169999}) is None
    assert check_review_lifetime(initial, WALL, {**CLOCK, "elapsed_ms": 170000}) is None
    long_window = start_review_lifetime(WALL, CLOCK, WALL + 86400000)
    assert long_window["expires_ms"] == WALL + REVIEW_LIFETIME_MS


def test_reads_or_transfer_to_another_process_cannot_restart_the_fifteen_minutes():
    initial = start_review_lifetime(WALL, CLOCK, WALL + 86400000)
    checked = check_review_lifetime(initial, WALL + 800000, {**CLOCK, "elapsed_ms": 850000})
    assert checked is not None and checked["expires_ms"] == initial["expires_ms"]
    assert checked["created_ms"] == initial["created_ms"] and checked["clock"] == initial["clock"]
    # A stalled wall clock, new process or delayed wake cannot recreate a fresh timer.
    assert check_review_lifetime(checked, WALL + 800000, {**CLOCK, "elapsed_ms": 950000}) is None


def test_reboot_missing_clock_and_rollback_never_release_an_older_review():
    initial = start_review_lifetime(WALL, CLOCK, WALL + 86400000)
    checked = check_review_lifetime(initial, WALL + 5000, {**CLOCK, "elapsed_ms": 55000})
    assert checked is not None
    assert check_review_lifetime(checked, WALL + 6000, None) is None
    assert (
        check_review_lifetime(checked, WALL + 6000, {"epoch": "f" * 32, "elapsed_ms": 55001})
        is None
    )
    assert check_review_lifetime(checked, WALL + 4999, {**CLOCK, "elapsed_ms": 55001}) is None
    assert check_review_lifetime(checked, WALL + 5001, {**CLOCK, "elapsed_ms": 54999}) is None


@pytest.mark.parametrize(
    "edit",
    [
        lambda x: x.update(expires_ms=WALL + REVIEW_LIFETIME_MS + 1),
        lambda x: x.update(expires_ms=WALL),
        lambda x: x.update(checked_ms=WALL - 1),
        lambda x: x.update(checked_elapsed_ms=49999),
        lambda x: x.update(checked_elapsed_ms=50000 + REVIEW_LIFETIME_MS),
        lambda x: x.update(created_ms=True),
        lambda x: x.update(extra="PRIVATE_SENTINEL"),
        lambda x: x["clock"].update(epoch="0" * 32),
        lambda x: x["clock"].update(elapsed_ms=2**53),
    ],
)
def test_malformed_or_extended_lifetimes_never_become_approval_authority(edit):
    value = copy.deepcopy(start_review_lifetime(WALL, CLOCK, WALL + 86400000))
    edit(value)
    with pytest.raises(ValueError, match="telemetry_review_clock_unavailable"):
        review_lifetime(value)
    assert check_review_lifetime(value, WALL, CLOCK) is None
