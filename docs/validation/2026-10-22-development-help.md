# Repository help in the development server

Verified on 22 October 2026 against Vite 8.3.4. This correction follows the frozen
4.45.0 release source; it does not change those release artifacts.

Opening the durable-capture guide through the frontend development server
returned raw Markdown with `Content-Type: text/markdown` for its JavaScript
module import. The browser rejected it. The packaged production help library
separately passed its build and navigation checks.

The frontend npm workspace does not contain the repository's documentation.
Vite's transform access check examines both the clean filename and the `?raw`
module identifier. Implicit import access was insufficient; allowing only the
clean filenames also left the root guides untransformed.

The development configuration now retains Vite's discovered workspace boundary
and explicitly allows `docs/`, `README.md`, `SECURITY.md`, `CONTRIBUTING.md` and
`studio/README.md`. Each individual guide also allows its exact raw module
identifier. Filesystem strictness and the existing deny rules remain enabled.
The entire repository is not added to the allowlist.

Actual loopback HTTP checks passed for the capture guide, roadmap and all four
individual guides: each import returned JavaScript with a default string export.
Four negative requests, covering ordinary and raw-module access to synthetic
unlisted files inside and outside the checkout, returned HTTP 403 without their
contents. The TypeScript project check passed. The temporary files and development
server were removed after verification.

This is development-server acceptance on Linux. The change affects the `server`
configuration only; native distribution and public-update qualification continue
through their separate release gates.
