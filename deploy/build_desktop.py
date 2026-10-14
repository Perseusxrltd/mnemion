"""Retry one transient Electron packaging download without relaxing build gates."""

from __future__ import annotations

from collections import deque
import os
import re
import subprocess
import sys
import time


def transient_download(log: str) -> bool:
    return bool(
        re.search(r"HTTPError: Response code (?:500|502|503|504)\b", log)
    ) and not re.search(
        r"checksum|integrity|signature|digest mismatch|ENOSPC|out of memory", log, re.IGNORECASE
    )


def build(command: list[str], *, pause=time.sleep) -> int:
    for attempt in range(2):
        tail = deque(maxlen=128)
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as child:
            while data := child.stdout.readline(8192):
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
                tail.append(data)
            code = child.wait()
        if (
            code == 0
            or attempt
            or not transient_download(b"".join(tail).decode("utf-8", errors="replace"))
        ):
            return code
        print(
            "Upstream packaging download returned a transient server error; retrying once.",
            flush=True,
        )
        pause(2)
    return 1


def main():
    command = ["npm", "--prefix", "studio/electron", "run", "dist"]
    if os.name == "nt":
        # This fixed command contains no interpolated input or package path.
        command = [
            os.path.join(os.environ["SystemRoot"], "System32", "cmd.exe"),
            "/d",
            "/c",
            "npm --prefix studio/electron run dist",
        ]
    raise SystemExit(build(command))


if __name__ == "__main__":
    main()
