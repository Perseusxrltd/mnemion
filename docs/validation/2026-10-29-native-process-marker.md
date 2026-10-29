# Native process-custody fixture readiness

On 29 October 2026, the first [4.46.53 native run](https://github.com/Perseusxrltd/mnemion/actions/runs/40896509541)
stopped on Mac ARM at `test_stopping_a_foreground_launcher_also_stops_its_verified_child`.
The original job log records `int(marker.read_text())` receiving an empty string
at 15:07:54 UTC. Sixteen other process checks passed in that job. The later
missing desktop scan artifact follows the early stop and is not a passing scan.

The synthetic launcher used `Path.write_text`, which creates the pathname before
writing the PID. Its observer treated pathname existence as readiness. The
fixture now writes to a sibling temporary path, closes it, and atomically
renames it to the observed path. No sleep increase, test retry, skip or process
ownership bypass is added. Product runtime code is unchanged by this correction.

The complete process-custody file passed **17 tests on Linux** with Python 3.12
and **17 on actual Windows** with Python 3.13, using the same corrected source.
This checks actual short-lived native processes, without a model or provider
call. The corrected candidate must still pass the required native release
matrix. It does not establish the separate affected-Mac launch acceptance for
issue 49. The first failed run remains retained.
