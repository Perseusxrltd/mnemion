# Desktop update retry validation — 2026-10-12

The actual Windows session reported **Update unavailable · retry scheduled**
after its normal startup check. One ordinary **Check for updates** action then
downloaded 4.1.3 successfully. Its 209,557,567-byte installer matched the already
verified public package, with SHA-256
`8e8f9f9bac955af9304e27940fe11f5ad487eb16dca7a44789c94f2834ece7fd`.
No error detail was captured that establishes why the first request failed.

Inspection confirmed that the desktop controller had no short retry timer;
the next automatic attempt depended on its normal six-hour interval. Version
4.1.5 adds bounded retries with a 0–25% scheduling spread. After three additional
failures, the normal interval remains the fallback. A successful result, user
pause or application exit clears pending retries.

All **106 Electron tests** passed: 97 existing component cases and nine
controller cases. The four new controller scenarios use the production
controller with controlled timers and a synthetic platform transport:

- Duplicate error notification and a rejected request schedule one retry;
  repeated failure follows the bounded delays, stops short retries, and accepts
  a fresh manual check.
- A successful retry stops further downloads while the actual controller's
  focus and work guards still prevent an unsafe installation.
- Pausing or quitting cancels retries, including late provider failure events.
- An outstanding provider check does not overlap a queued manual request;
  its successful follow-up clears the failed attempt's timer.

These tests do not bypass or replace native signature, installer or public-feed
checks. The 4.1.5 release gates and actual installed retry observation remain
pending. The preceding Windows download used an explicit retry; it is not
presented as proof of the new automatic retry behavior.
