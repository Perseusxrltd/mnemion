"""Read one admission receipt.

validate_receipt() only checks that the file matches the verdict rules.
That consistency flag is not an admission verdict. This script also requires
the admit exit rule: reason none, collection off, no owned summaries, and
the mode exit. A missing, unreadable, or wrong-sized file fails. It does not
load BPF or touch a cgroup.
"""

from __future__ import annotations

import sys
from pathlib import Path

from receipt import CONST, Receipt, mode_exit_ok, validate_receipt


def _fail(detail: str) -> int:
    print(detail)
    print("receipt_consistent=0")
    print("receipt_consistent_is_not_the_admission_verdict=1")
    print("admission_verdict=fail")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: admit_observe.py <receipt>")
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print("receipt_missing=1")
        return _fail("receipt_read_error=0")
    expected = int(CONST["LIFETIME_RECEIPT_BYTES"])
    try:
        with path.open("rb") as handle:
            blob = handle.read(expected + 1)
    except OSError:
        return _fail("receipt_read_error=1")
    if len(blob) != expected:
        print("receipt_length=%d" % len(blob))
        return _fail("receipt_read_error=0")
    consistent = validate_receipt(blob)
    print("receipt_consistent=%d" % (1 if consistent["ok"] else 0))
    print("receipt_consistent_is_not_the_admission_verdict=1")
    if not consistent["ok"]:
        print("admission_verdict=fail")
        return 1
    raw = Receipt.from_buffer_copy(blob)
    exit_ok = mode_exit_ok(raw)
    print("mode=%d" % int(raw.mode))
    print("reason=%d" % int(raw.reason))
    print("collection_enabled=%d" % int(raw.collection_enabled))
    print("summary_count=%d" % int(raw.summary_count))
    print("coverage_pass=%d" % int(raw.coverage_pass))
    print("fixture_launched=%d" % int(raw.fixture_launched))
    print("support_admitted=%d" % int(raw.support_admitted))
    print("direct_launch_ok=%d" % int(raw.direct_launch_ok))
    print("cleanup_pass=%d" % int(raw.cleanup_pass))
    print("observation_failed=%d" % int(raw.observation_failed))
    print("mode_exit_ok=%d" % (1 if exit_ok else 0))
    admitted = (
        exit_ok
        and int(raw.mode) == CONST["LIFETIME_MODE_ADMIT"]
        and int(raw.reason) == CONST["LIFETIME_REASON_NONE"]
        and int(raw.collection_enabled) == 0
        and int(raw.summary_count) == 0
        and int(raw.coverage_pass) == 0
        and int(raw.fixture_launched) == 0
        and int(raw.resource_acceptance) == 0
        and int(raw.budget_comparison_allowed) == 0
    )
    print("admission_verdict=%s" % ("pass" if admitted else "fail"))
    return 0 if admitted else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
