"""Maintainer export of closed v3 weeks. Not a local privacy-settings page.

The command reads an already sealed publisher store. It does not enable
collection, contact a provider, or treat report ticks as people.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import sqlite3

from . import policy
from .aggregate_v3 import validate
from .publication_v3 import ReportStore
from .utility_v3 import modelled_utility
from .wire_v3 import METRICS, METRIC_BY_ID, WireV3Error, bucket_label


def honest_summary(reports: list[dict], publication_failures: list[dict] | None = None) -> dict:
    failures = [] if publication_failures is None else publication_failures
    if any(
        type(item) is not dict
        or set(item) != {"window_week", "state"}
        or item["state"] != "publication_failed"
        or type(item["window_week"]) is not int
        for item in failures
    ):
        raise WireV3Error
    # Package disclosure for this exporting build. A sealed report is not a probe.
    configured = policy.disclosure()
    return {
        "surface": "maintainer_export",
        "ordinary_privacy_settings_contain_fleet_data": False,
        "reports_are_not_unique_people": True,
        "noise_is_not_independent_user_or_causal_inference": True,
        "v2_local_privacy": False,
        "collection_available": configured["collection_available"],
        "destination": configured["destination"],
        "collection_fields_describe_exporting_build_configuration": True,
        "collection_fields_are_live_collector_or_network_observation": False,
        "report_count": len(reports),
        "publication_failures": failures,
        "limitations": modelled_utility()["limitations"],
    }


def _export_spec(report: dict, metric_id: str) -> dict:
    saved = next(item for item in report["domain"]["metric_legend"] if item["id"] == metric_id)
    compiled = METRIC_BY_ID[metric_id]
    if saved["kind"] == "ordered":
        return {**compiled, "upper_bounds": saved["upper_bounds"], "unit": saved["unit"]}
    return compiled


def _rows(report: dict) -> list[dict]:
    rows = []

    def emit(scope: str, axis: str, cohort_id: str, metrics: list[dict], state: str):
        for metric in metrics:
            spec = _export_spec(report, metric["id"])
            for index, count in enumerate(metric["counts"]):
                rows.append(
                    {
                        "week": report["window_week"],
                        "scope": scope,
                        "axis": axis,
                        "cohort_id": cohort_id,
                        "metric": metric["id"],
                        "bucket": bucket_label(spec, index),
                        "noisy_count": count,
                        "publication_state": state,
                    }
                )

    emit("global", "full_domain", "", report["global"]["metrics"], "noisy_full_domain_sum")
    for cohort in report["cohorts"]:
        emit("cohort", cohort["axis"], cohort["id"], cohort["metrics"], "published_noisy_cohort")
    remainder = report["suppressed_remainder"]
    if remainder is not None:
        for axis_row in remainder["axes"]:
            emit(
                "remainder",
                axis_row["axis"],
                "+".join(axis_row["ids"]),
                axis_row["metrics"],
                "combined_suppressed_cohorts",
            )
    return rows


def _json_island(value: object) -> str:
    """JSON for a non-executed script block. ``<`` cannot close the HTML tag."""
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    island = (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    if "<" in island or "__ISLAND__" in island:
        raise WireV3Error
    return island


def _series(report: dict, metrics: list[dict]) -> list[dict]:
    rows = []
    for metric in metrics:
        spec = _export_spec(report, metric["id"])
        item = {
            "id": metric["id"],
            "buckets": [
                {"label": bucket_label(spec, index), "count": count}
                for index, count in enumerate(metric["counts"])
            ],
        }
        if "quantiles" in metric:
            item["quantiles"] = metric["quantiles"]
        rows.append(item)
    if len(rows) != len(METRICS):
        raise WireV3Error
    return rows


def _view(reports: list[dict], summary: dict) -> dict:
    """Separate release and OS rows already stored on each sealed report.

    The page does not add those axes, pool raw counters, or redraw a quantile.
    """
    weeks = []
    for report in reports:
        remainder = {"release": None, "os": None}
        suppressed = report["suppressed_remainder"]
        if suppressed is not None:
            for axis_row in suppressed["axes"]:
                remainder[axis_row["axis"]] = {
                    "ids": list(axis_row["ids"]),
                    "denominator": axis_row["denominator"],
                    "metrics": _series(report, axis_row["metrics"]),
                    "quantiles": axis_row["quantiles"],
                }
        weeks.append(
            {
                "week": report["window_week"],
                "frozen_legend": report["domain"]["metric_legend"],
                "report_unit": report["report_unit"],
                "comparisons": report["comparisons"],
                "noise_uncertainty_is_not": report["noise_uncertainty_is_not"],
                "domain_label": report["global"]["label"],
                "domain_denominator": report["global"]["denominator"],
                "domain_metrics": _series(report, report["global"]["metrics"]),
                "release": [
                    {
                        "id": row["id"],
                        "slot": row["slot"],
                        "denominator": row["denominator"],
                        "metrics": _series(report, row["metrics"]),
                    }
                    for row in report["cohorts"]
                    if row["axis"] == "release"
                ],
                "os": [
                    {
                        "id": row["id"],
                        "slot": row["slot"],
                        "denominator": row["denominator"],
                        "metrics": _series(report, row["metrics"]),
                    }
                    for row in report["cohorts"]
                    if row["axis"] == "os"
                ],
                "remainder": remainder,
            }
        )
    return {
        "surface": "private_maintainer_export",
        "ordinary_privacy_settings_contain_fleet_data": False,
        "reports_are_not_unique_people": True,
        "noise_is_not_a_population_or_causal_confidence_interval": True,
        "publication_failures": summary["publication_failures"],
        "weeks": weeks,
    }


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; font-src 'none'">
<title>Private fleet report</title>
<style>
/* Colors from studio/frontend/src/index.css. Font files are not loaded. */
:root {
  color-scheme: dark;
  --ink: #02050d;
  --ink-soft: #070b14;
  --ivory: #f2ead9;
  --ivory-muted: #b9b1a4;
  --gold: #c49a55;
  --gold-bright: #e2b967;
  --line: rgba(196, 154, 85, .34);
  --line-soft: rgba(242, 234, 217, .13);
  --danger: #e57972;
  --surface-raised: #0a0f19;
  --surface-overlay: #0e1520;
  --surface-float: #111b28;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: radial-gradient(circle at 88% 8%, rgba(21, 36, 58, .28), transparent 28rem), var(--ink);
  color: var(--ivory);
  font-family: Arial, sans-serif;
  font-size: 14px;
  line-height: 1.5;
}
main { max-width: 920px; margin: 0 auto; padding: 28px 20px 64px; }
h1, h2, h3 { font-weight: 560; letter-spacing: -.025em; }
h1 { font-size: 28px; margin: 0 0 8px; }
h2 { font-size: 18px; margin: 28px 0 8px; color: var(--gold-bright); }
p, li { color: var(--ivory-muted); }
.banner, .panel, .metric {
  background: var(--surface-overlay);
  border: 1px solid var(--line-soft);
  border-radius: 6px;
  padding: 14px 16px;
  margin: 12px 0;
}
.banner { border-color: var(--line); background: var(--ink-soft); }
form { display: flex; flex-wrap: wrap; gap: 16px; align-items: end; }
label, legend { color: var(--ivory); }
fieldset { border: 1px solid var(--line); border-radius: 4px; margin: 0; padding: 8px 12px; }
select {
  display: block;
  min-width: 220px;
  margin-top: 4px;
  background: var(--surface-float);
  color: var(--ivory);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 8px;
}
:focus-visible { outline: 2px solid var(--gold-bright); outline-offset: 1px; }
.bucket { display: grid; grid-template-columns: minmax(8rem, 14rem) 5rem 1fr; gap: 8px; align-items: center; margin: 3px 0; }
.bar { display: block; height: 8px; background: var(--gold); border-radius: 4px; }
.bar.neg { background: var(--danger); }
.count { font-variant-numeric: tabular-nums; color: var(--ivory); }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--line-soft); }
svg { width: 100%; height: auto; display: block; margin: 8px 0; }
#empty[hidden] { display: none; }
</style>
</head>
<body>
<main>
<h1>Private fleet report</h1>
<p class="banner">Local maintainer export. These figures are noisy report ticks. They are not unique people. A release row and an operating-system row are separate selections and are not a joined profile. p50 and p95, when shown, are catalog bucket bounds. They are not a population or causal confidence interval, and they are not a precise quantile.</p>
<form>
<label for="week">Week
<select id="week"></select>
</label>
<fieldset>
<legend>Cohort axis</legend>
<label><input type="radio" name="axis" value="release" checked> Release</label>
<label><input type="radio" name="axis" value="os"> Operating system</label>
<label><input type="radio" name="axis" value="domain"> Full-domain sum</label>
</fieldset>
<label for="cohort">Cohort on the selected axis
<select id="cohort"></select>
</label>
</form>
<section id="empty" class="panel">
<h2>No closed weeks</h2>
<p>This store has no sealed week to inspect. Publication failures, if any, are listed below. There is no fleet total to invent.</p>
</section>
<h2>Publication failures</h2>
<ul id="failures"></ul>
<section id="detail" hidden>
<p id="denominator"></p>
<h2>Noisy denominator across closed weeks</h2>
<div id="trend"></div>
<h2>Metric distributions</h2>
<div id="metrics"></div>
</section>
</main>
<script type="application/json" id="fleet-report">__ISLAND__</script>
<script>
(function () {
  var data = JSON.parse(document.getElementById("fleet-report").textContent);
  var weekSel = document.getElementById("week");
  var cohortSel = document.getElementById("cohort");
  var failures = document.getElementById("failures");
  var empty = document.getElementById("empty");
  var detail = document.getElementById("detail");
  var denominator = document.getElementById("denominator");
  var trend = document.getElementById("trend");
  var metrics = document.getElementById("metrics");
  var svgNs = "http://www.w3.org/2000/svg";

  function el(tag, className, value) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (value != null) node.textContent = String(value);
    return node;
  }
  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }
  function axis() {
    var picked = document.querySelector('input[name="axis"]:checked');
    return picked ? picked.value : "release";
  }
  function currentWeek() {
    for (var i = 0; i < data.weeks.length; i += 1) {
      if (String(data.weeks[i].week) === weekSel.value) return data.weeks[i];
    }
    return null;
  }
  function fillWeeks() {
    clear(weekSel);
    if (!data.weeks.length) {
      var none = el("option", null, "No closed weeks");
      none.value = "";
      weekSel.appendChild(none);
      weekSel.disabled = true;
      return;
    }
    weekSel.disabled = false;
    var ordered = data.weeks.slice().sort(function (a, b) { return a.week - b.week; });
    ordered.forEach(function (week) {
      var option = el("option", null, "Week " + week.week);
      option.value = String(week.week);
      weekSel.appendChild(option);
    });
    weekSel.value = String(ordered[ordered.length - 1].week);
  }
  function memberKey(ids) {
    return JSON.stringify(ids.slice().sort());
  }
  function weekSpan() {
    var first = data.weeks[0].week;
    var last = first;
    for (var i = 1; i < data.weeks.length; i += 1) {
      if (data.weeks[i].week < first) first = data.weeks[i].week;
      if (data.weeks[i].week > last) last = data.weeks[i].week;
    }
    return { first: first, last: last };
  }
  function fillCohorts() {
    var previousIdentity = cohortSel.selectedIndex >= 0 ? cohortSel.options[cohortSel.selectedIndex].textContent : "";
    var previousValue = cohortSel.value;
    clear(cohortSel);
    var week = currentWeek();
    var picked = axis();
    var radios = document.querySelectorAll('input[name="axis"]');
    for (var r = 0; r < radios.length; r += 1) radios[r].disabled = !week;
    if (!week || picked === "domain") {
      cohortSel.disabled = true;
      var unused = el("option", null, picked === "domain" ? "Full domain is not a cohort" : "No cohort");
      unused.value = "";
      cohortSel.appendChild(unused);
      return;
    }
    var rows = week[picked] || [];
    rows.forEach(function (row) {
      var option = el("option", null, row.id);
      option.value = String(row.slot);
      cohortSel.appendChild(option);
    });
    var remainder = week.remainder && week.remainder[picked];
    if (remainder) {
      var grouped = el("option", null, "Suppressed remainder " + remainder.ids.join(" + "));
      grouped.value = "remainder";
      cohortSel.appendChild(grouped);
    }
    if (!cohortSel.options.length) {
      var missing = el("option", null, "No cohort on this axis");
      missing.value = "";
      cohortSel.appendChild(missing);
    }
    cohortSel.disabled = cohortSel.options.length === 0 || cohortSel.options[0].value === "";
    var matched = false;
    for (var i = 0; i < cohortSel.options.length; i += 1) {
      if (previousIdentity !== "" && cohortSel.options[i].textContent === previousIdentity) {
        cohortSel.selectedIndex = i;
        matched = true;
        break;
      }
    }
    if (!matched && previousValue === "remainder") {
      for (var j = 0; j < cohortSel.options.length; j += 1) {
        if (cohortSel.options[j].value === "remainder") cohortSel.selectedIndex = j;
      }
    }
  }
  function selection() {
    var week = currentWeek();
    var picked = axis();
    if (!week) return null;
    if (picked === "domain") {
      return {
        denominator: week.domain_denominator,
        metrics: week.domain_metrics,
        quantileNote: null,
        label: week.domain_label
      };
    }
    if (cohortSel.value === "remainder") {
      var row = week.remainder[picked];
      if (!row) return null;
      return {
        denominator: row.denominator,
        metrics: row.metrics,
        quantileNote: row.quantiles,
        label: "suppressed remainder " + row.ids.join(" + "),
        members: row.ids.slice()
      };
    }
    var slot = Number(cohortSel.value);
    var found = (week[picked] || []).filter(function (item) { return item.slot === slot; })[0];
    if (!found) return null;
    return { denominator: found.denominator, metrics: found.metrics, quantileNote: null, label: found.id };
  }
  function trendPoints() {
    var picked = axis();
    var week = currentWeek();
    if (!week) return [];
    var identity = null;
    if (picked !== "domain" && cohortSel.value !== "remainder") {
      var slot = Number(cohortSel.value);
      var found = (week[picked] || []).filter(function (item) { return item.slot === slot; })[0];
      identity = found ? found.id : null;
    }
    var points = [];
    data.weeks.forEach(function (item) {
      if (picked === "domain") {
        points.push({ week: item.week, value: item.domain_denominator });
        return;
      }
      if (cohortSel.value === "remainder") {
        var selected = week.remainder && week.remainder[picked];
        var key = selected ? memberKey(selected.ids) : "";
        var grouped = item.remainder && item.remainder[picked];
        if (grouped && memberKey(grouped.ids) === key) {
          points.push({ week: item.week, value: grouped.denominator });
        }
        return;
      }
      var row = (item[picked] || []).filter(function (entry) { return entry.id === identity; })[0];
      if (row) points.push({ week: item.week, value: row.denominator });
    });
    points.sort(function (a, b) { return a.week - b.week; });
    return points;
  }
  function boundText(metric, key) {
    var item = metric.quantiles[key];
    if (!item) return key + ": missing";
    if (item.state === "insufficient_precision") {
      return key + ": insufficient_precision. Mechanism envelope, not a population or causal confidence interval.";
    }
    if (item.state === "bucket_bounds") {
      var low = Object.prototype.hasOwnProperty.call(item, "lower_inclusive")
        ? String(item.lower_inclusive) + " inclusive"
        : String(item.lower_exclusive) + " exclusive";
      var high = item.upper_inclusive == null ? "open" : String(item.upper_inclusive) + " inclusive";
      return key + " bucket bounds: " + low + " to " + high + " " + item.unit + ". Not a precise quantile.";
    }
    return key + ": " + item.state;
  }
  function drawTrend(points, memberNote) {
    clear(trend);
    if (memberNote) trend.appendChild(el("p", "members", memberNote));
    if (!points.length) {
      trend.appendChild(el("p", null, "No noisy denominator for this selection."));
      return;
    }
    var values = points.map(function (point) { return point.value; });
    var low = Math.min.apply(null, values.concat([0]));
    var high = Math.max.apply(null, values.concat([0]));
    if (low === high) { low -= 1; high += 1; }
    var width = 640;
    var height = 160;
    var pad = 16;
    var span = weekSpan();
    var svg = document.createElementNS(svgNs, "svg");
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("aria-hidden", "true");
    var coords = points.map(function (point) {
      var x = span.last === span.first
        ? width / 2
        : pad + (point.week - span.first) * (width - 2 * pad) / (span.last - span.first);
      var y = pad + (high - point.value) * (height - 2 * pad) / (high - low);
      return x.toFixed(1) + "," + y.toFixed(1);
    });
    var line = document.createElementNS(svgNs, "polyline");
    line.setAttribute("points", coords.join(" "));
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", "#e2b967");
    line.setAttribute("stroke-width", "2");
    svg.appendChild(line);
    trend.appendChild(svg);
    var table = el("table");
    table.appendChild(el("caption", null, "Noisy report denominator by closed week. Not a count of people."));
    points.forEach(function (point) {
      var row = el("tr");
      var head = el("th", null, "Week " + point.week);
      head.scope = "row";
      row.appendChild(head);
      row.appendChild(el("td", null, String(point.value)));
      table.appendChild(row);
    });
    trend.appendChild(table);
  }
  function draw() {
    clear(failures);
    if (!data.publication_failures.length) {
      failures.appendChild(el("li", null, "No publication failures in the retained windows."));
    } else {
      data.publication_failures.forEach(function (item) {
        failures.appendChild(el("li", null, "Week " + item.window_week + ": " + item.state));
      });
    }
    fillCohorts();
    var picked = selection();
    empty.hidden = data.weeks.length > 0;
    detail.hidden = !picked;
    if (!picked) return;
    denominator.textContent = picked.label + " noisy denominator " + picked.denominator + ". Not unique people.";
    var memberNote = picked.members
      ? "Member set: " + picked.members.join(" + ") + ". Weeks with a different suppressed set are not connected."
      : null;
    drawTrend(trendPoints(), memberNote);
    clear(metrics);
    picked.metrics.forEach(function (metric) {
      var section = el("section", "metric");
      section.appendChild(el("h3", null, metric.id));
      var disabled = metric.buckets.filter(function (bucket) { return bucket.label === "group_disabled"; })[0];
      var missing = metric.buckets.filter(function (bucket) { return bucket.label === "sensor_missing"; })[0];
      if (disabled) section.appendChild(el("p", null, "group_disabled: " + disabled.count));
      if (missing) section.appendChild(el("p", null, "sensor_missing: " + missing.count));
      if (picked.quantileNote) {
        section.appendChild(el("p", null, "Quantiles: " + picked.quantileNote + ". Not a single population."));
      } else if (metric.quantiles) {
        section.appendChild(el("p", null, boundText(metric, "p50")));
        section.appendChild(el("p", null, boundText(metric, "p95")));
      } else {
        section.appendChild(el("p", null, "No p50 or p95. This metric is not an ordered measurement."));
      }
      var peak = 1;
      metric.buckets.forEach(function (bucket) { peak = Math.max(peak, Math.abs(bucket.count)); });
      metric.buckets.forEach(function (bucket) {
        var row = el("div", "bucket");
        row.appendChild(el("span", "label", bucket.label));
        row.appendChild(el("span", "count", String(bucket.count)));
        var bar = el("span", bucket.count < 0 ? "bar neg" : "bar");
        bar.style.width = Math.round(Math.abs(bucket.count) / peak * 100) + "%";
        row.appendChild(bar);
        section.appendChild(row);
      });
      metrics.appendChild(section);
    });
  }
  fillWeeks();
  document.querySelectorAll('input[name="axis"]').forEach(function (input) {
    input.addEventListener("change", draw);
  });
  weekSel.addEventListener("change", draw);
  cohortSel.addEventListener("change", draw);
  draw();
})();
</script>
</body>
</html>
"""


def _page(view: dict) -> str:
    return _PAGE.replace("__ISLAND__", _json_island(view), 1)


def render(
    reports: list[dict], export_format: str, publication_failures: list[dict] | None = None
) -> str:
    checked = [validate(report) for report in reports]
    summary = honest_summary(checked, publication_failures)
    if export_format == "json":
        return json.dumps({"summary": summary, "reports": checked}, indent=2, allow_nan=False)
    if export_format == "html":
        return _page(_view(checked, summary))
    if export_format != "csv":
        raise WireV3Error
    buffer = io.StringIO()
    summary_writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "record",
            "ordinary_privacy_settings_contain_fleet_data",
            "reports_are_not_unique_people",
            "noise_is_not_independent_user_or_causal_inference",
            "report_count",
            "publication_failure_weeks",
        ),
    )
    summary_writer.writeheader()
    summary_writer.writerow(
        {
            "record": "summary",
            "ordinary_privacy_settings_contain_fleet_data": False,
            "reports_are_not_unique_people": True,
            "noise_is_not_independent_user_or_causal_inference": True,
            "report_count": summary["report_count"],
            "publication_failure_weeks": "+".join(
                str(item["window_week"]) for item in summary["publication_failures"]
            ),
        }
    )
    buffer.write("\n")
    rows = [row for report in checked for row in _rows(report)]
    writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "week",
            "scope",
            "axis",
            "cohort_id",
            "metric",
            "bucket",
            "noisy_count",
            "publication_state",
        ),
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse echoes the rejected value. Paths and credentials stay out of the message.
        raise WireV3Error


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Export sealed v3 telemetry reports or the utility model")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--format", choices=("json", "csv", "html"))
    parser.add_argument("--utility", action="store_true")
    try:
        args = parser.parse_args(argv)
        if args.utility:
            if args.state is not None or args.format not in (None, "json"):
                raise WireV3Error
            print(json.dumps(modelled_utility(), indent=2, allow_nan=False))
            return 0
        if (
            args.state is None
            or not args.state.is_absolute()
            or args.state.is_symlink()
            or args.format is None
            or not (args.state / "reports-v3.sqlite3").is_file()
        ):
            raise WireV3Error
        store = ReportStore(args.state)
        print(render(store.reports(), args.format, store.publication_failures()))
        return 0
    except (OSError, ValueError, WireV3Error, sqlite3.DatabaseError):
        print(json.dumps({"ok": False, "error": "telemetry_v3_export_rejected"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
