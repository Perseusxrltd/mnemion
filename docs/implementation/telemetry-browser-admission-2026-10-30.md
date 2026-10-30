# Telemetry admission across browsers and networks

30 October 2026. Approved design for V08 implementation and qualification.
**This decision does not activate collection or establish browser acceptance.**

The current browser owner requires both `PressureObserver` and
`performance.memory`. Firefox and Safari do not implement these APIs according
to the [PressureObserver compatibility data](https://github.com/mdn/browser-compat-data/blob/main/api/PressureObserver.json)
and [Performance compatibility data](https://github.com/mdn/browser-compat-data/blob/main/api/Performance.json)
retrieved on 30 October. The browser also normally reports an unknown network
tariff, which automatic mode currently rejects. These defaults prevent delivery
even when a visible, online page has no observed restriction.

## Network decision

Python, desktop and browser reservation and final-send checks must use the same
decision, after all other permission, resource and traffic-budget checks pass:

| Saved connection mode | Observed network | Permit a bounded attempt |
| --- | --- | --- |
| Automatic | Unknown or unmetered | Yes |
| Unmetered | Unknown or unmetered | Yes |
| Automatic or unmetered | Metered | No |
| Metered | Any | No |

Unknown stays unknown; it does not mean free data. Invalid condition objects
and observed resource constraints still refuse delivery. Native pressure
checks, sticky restrictions, reservations and traffic limits remain unchanged.

## Browser capability limits

An absent pressure API or a recognized unsupported/permission-denied capability
response means that sensor is unavailable. It does not invent a nominal reading.
If the sensor is supported, delivery still requires bounded initialization and
a fresh nominal observation. Stale or malformed readings, unexpected errors,
startup timeouts and observed pressure refuse the attempt.

An absent heap API adds no heap-pressure veto or fabricated measurement. A
present API must pass numeric validation and the existing 80% threshold.
Throwing getters and malformed data refuse. A previously observed restriction
cannot disappear solely because its API disappears or an observer closes;
valid fresh observations must clear it.

Offline or hidden pages, page exit, data-saving mode, cellular or otherwise
known metered connections, slow links and cancellation remain restrictive.
Observers only accompany offered work in an already-awake page. There is no
new idle service. Missing measurements retain the existing missing-sensor
representation; the wire format gains no identifying capability fields.

## Disclosure and saved choices

Changing automatic mode requires disclosure version 3 and a fresh explicit
acknowledgement for an enabled installation that acknowledged version 2.
Connection-setting edits must not acknowledge the new disclosure. Old held
reports and approvals must not authorize the new behavior.

The app must explain that automatic sending can use a connection whose cost
cannot be detected; available metering, data-saving and pressure signals pause
sending, some browsers cannot report those signals, and traffic limits still
apply. This is not a guarantee of free network use.

Opt-out, manual review, company restrictions, Global Privacy Control and spent
budgets remain. Acknowledgement clears old pending/held data through the normal
configuration path without refunding attempts. Production collection, its
destination and its route remain disabled/unconfigured until separately
qualified.

## Required evidence

Focused tests cover the common truth table, version migration, absent APIs,
supported-sensor failures, sticky restrictions and cancellation. Restrictions
introduced after reservation must still prevent the final handoff and retain
the spent attempt. Real Firefox and WebKit journeys must run without fake
sensors; WebKit-engine evidence does not qualify a native Safari installation.

Installed delivery, the [resource budget](telemetry-resource-budget-2026-10-30.md),
whole-wire accounting, operated collector privacy and useful fleet reports
remain independent requirements. No historical failure is rescored.
