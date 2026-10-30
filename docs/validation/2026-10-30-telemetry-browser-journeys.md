# Browser journey source qualification

30 October 2026. The manual Firefox and WebKit diagnostic is reviewed source;
its actual browser journeys have not yet passed. Production collection remains
off and V08 remains Building.

Actual Grok candidate `29c8ad1fcbcec1acf3a378474c8b241a0d221443` was frozen
when its bounded implementation job ended. Astra corrected the output-directory
handoff, opened the selected search result's collapsed ranking explanation,
and gave the engines separate lexical queries. The content canary now fits
inside a 25-byte packet, so its exclusion check can detect an injected leak.

The first focused source selection passed 32 cases and failed one fixture
directory creation. After correcting creation of the shared parent directory,
that one case passed. These are 33 distinct qualified cases across the retained
original and corrected runs, including the Node driver syntax check. They are
not a final rerun of the complete selection or browser execution evidence.

The [journey design](../implementation/telemetry-browser-journeys-2026-10-30.md)
uses the normal built frontend and a real private memory API. Each engine gets
one fresh profile and one finite journey. Only a successful hosted receipt can
qualify delivery. Playwright WebKit on Linux does not qualify native Safari;
resource and production acceptance remain separate.
