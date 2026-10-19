"""Bounded subprocess transport for operator-approved Git and scanner programs."""

import os
import signal
import subprocess
import threading
import time

from .format import JournalError


def program_environment():
    allowed = {
        "path",
        "home",
        "user",
        "logname",
        "userprofile",
        "homedrive",
        "homepath",
        "systemroot",
        "systemdrive",
        "windir",
        "comspec",
        "pathext",
        "appdata",
        "localappdata",
        "programdata",
        "programfiles",
        "programfiles(x86)",
        "programw6432",
        "temp",
        "tmp",
        "tmpdir",
        "lang",
        "lc_all",
        "lc_ctype",
        "tz",
        "xdg_config_home",
        "xdg_data_home",
        "xdg_cache_home",
        "xdg_runtime_dir",
        "dbus_session_bus_address",
        "https_proxy",
        "http_proxy",
        "all_proxy",
        "no_proxy",
        "ssl_cert_file",
        "ssl_cert_dir",
        "curl_ca_bundle",
        "requests_ca_bundle",
        "gcm_credential_store",
        "dotnet_root",
    }
    return {key: value for key, value in os.environ.items() if key.casefold() in allowed}


def run(args, *, input=None, env=None, cwd=None, timeout=30, maximum=1024 * 1024, cancel=None):
    if cancel is not None and cancel.is_set():
        raise JournalError("journal_program_interrupted")
    try:
        child = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=program_environment() if env is None else env,
            cwd=cwd,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
    except OSError:
        raise JournalError("journal_program_unavailable") from None
    output = bytearray()
    failed = threading.Event()

    def stop():
        if os.name == "nt" and child.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill.exe", "/PID", str(child.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                os.killpg(child.pid, signal.SIGKILL)
        except (OSError, subprocess.TimeoutExpired):
            if child.poll() is None:
                child.kill()

    def read(pipe, limit, save):
        size = 0
        try:
            while chunk := pipe.read1(65536):
                size += len(chunk)
                if size > limit:
                    failed.set()
                    stop()
                    break
                if save:
                    output.extend(chunk)
        except (OSError, ValueError):
            failed.set()
        finally:
            pipe.close()

    def write():
        try:
            child.stdin.write(input)
        except (OSError, ValueError):
            failed.set()
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass

    threads = [
        threading.Thread(target=read, args=(child.stdout, maximum, True), daemon=True),
        threading.Thread(target=read, args=(child.stderr, 65536, False), daemon=True),
    ]
    if input is not None:
        threads.append(threading.Thread(target=write, daemon=True))
    for thread in threads:
        thread.start()
    try:
        deadline = time.monotonic() + timeout
        while child.poll() is None:
            if time.monotonic() >= deadline or cancel is not None and cancel.is_set():
                raise subprocess.TimeoutExpired("journal program", timeout)
            try:
                child.wait(timeout=min(0.2, max(0.001, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                continue
    except subprocess.TimeoutExpired:
        stop()
        child.wait(timeout=5)
        raise JournalError("journal_program_interrupted") from None
    except BaseException:
        stop()
        child.wait(timeout=5)
        raise
    finally:
        for thread in threads:
            thread.join(1)
    if failed.is_set() or any(thread.is_alive() for thread in threads):
        stop()
        raise JournalError("journal_program_io_failed")
    return child.returncode, bytes(output)
