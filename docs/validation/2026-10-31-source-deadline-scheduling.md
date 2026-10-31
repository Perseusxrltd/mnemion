# Desktop source deadline scheduling

31 October 2026. Reviewed source:
`2857beaf2eb3e605f68d80bf4e6b64f19e43d6c9`. Its reviewed code matches
the original Grok candidate used for the checks below.

The earlier two-second tick already returned before file, native, credential
or network work when no enabled source was due. The change replaces those
idle timer wakeups with one unref'd deadline timer. Empty or fully paused
source lists leave no timer armed; the started state remains independent of
whether a timer exists. Existing scan intervals and helper RAM feedback stay
unchanged.

Automatic follow-up work already due retains two-second pacing. If stored
deadlines are unusable and no usable earliest deadline exists, the fallback
uses a source scan interval, bounded by the timer limit. Invalid current-clock
readings are handled separately; the controlled-clock case recorded a
two-second retry without starting credential or network work. A backwards
clock jump exercised the timer's maximum delay rather than a zero-delay loop.

Strict TypeScript compilation (`tsc -p studio/electron/tsconfig.json`)
exited 0. The first Node test invocation stopped with
`SyntaxError: Identifier 'settings' has already been declared` in a fixture;
that original failure is retained. After correcting the binding,
`node --test scripts/test-desktop-sources.mjs` from `studio/electron` passed
**110 tests in 862.7987 ms**. The passing checks were not rerun.

The source suite includes controlled-time cases for idle and paused lists,
future deadlines, manual Sync, one active scan and due-work pacing, wakes
during preview/reload, repair deferral, update suspension/resume, close and
late callbacks, clock changes and unref'd timers. Existing source and capture
recovery checks retain their scope.

These are source and lifecycle results, not CPU/RAM measurements or a release
qualification. F06/R04 remains partial; all 66 requirement states and resource
allowances are unchanged. Production telemetry remains off. Full process
coverage and the actual fixed-work CPU/RAM comparison remain open.
