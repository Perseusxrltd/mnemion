"""Print the fixed v3 client packets used by the TypeScript parity check."""

from __future__ import annotations

import json
from pathlib import Path

from mnemion.product_telemetry import catalog
from mnemion.product_telemetry.wire_v3 import WireV3Error, prepare, summarize


def _draws(values):
    state = {"n": 0}

    def random_below(limit):
        if state["n"] >= len(values):
            raise AssertionError("extra draw")
        value = values[state["n"]]
        state["n"] += 1
        if type(value) is not int or not 0 <= value < limit:
            raise AssertionError((value, limit))
        return value

    return random_below, lambda: state["n"]


def _rows(case):
    if "repeat" in case:
        return [(0, 1)] * case["repeat"]
    if "rows" in case:
        return case["rows"]
    if "rows_from" in case:
        rows = []
        for item in case["rows_from"]:
            _contribution, cells = catalog.observation(item["observation"])
            picked = [cell for cell in cells if catalog.describe(cell)["metric"] == item["metric"]]
            if len(picked) != 1:
                raise AssertionError(item["metric"])
            rows.append([picked[0], item["count"]])
        return rows
    totals = {}
    order = []
    for item in case.get("observations", []):
        _contribution, cells = catalog.observation(item)
        for cell in cells:
            if cell not in totals:
                order.append(cell)
                totals[cell] = 0
            totals[cell] += 1
    return [[cell, totals[cell]] for cell in order]


def _call(function, case, rows):
    random_below, used = _draws(case["draws"])
    packet = function(
        case["observations"] if function is summarize else rows,
        groups=case.get("groups", ["usage", "reliability", "performance", "resources"]),
        release=tuple(case.get("release", (4, 46, 53))),
        operating_system=case.get("operating_system", "linux"),
        random_below=random_below,
    )
    if used() != len(case["draws"]):
        raise AssertionError(case["name"])
    return packet


def main():
    fixture = Path(__file__).parents[1] / "tests/fixtures/telemetry-v3-client-vectors.json"
    document = json.loads(fixture.read_text())
    output = []
    for case in document["cases"]:
        rows = _rows(case)
        item = {"name": case["name"]}
        if case.get("error"):
            try:
                _call(prepare, case, rows)
            except WireV3Error:
                item["error"] = True
            else:
                raise SystemExit(f"expected error: {case['name']}")
        else:
            item["prepare"] = _call(prepare, case, rows).hex()
            if "observations" in case:
                item["summarize"] = _call(summarize, case, rows).hex()
        output.append(item)
    print(json.dumps(output))


if __name__ == "__main__":
    main()
