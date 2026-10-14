import sys

from deploy.build_desktop import build, transient_download


def test_transient_download_retries_once_and_propagates_the_actual_build_result(tmp_path):
    child = tmp_path / "download.py"
    counter = tmp_path / "attempts"
    child.write_text(
        "import sys\nfrom pathlib import Path\np=Path(sys.argv[1])\n"
        "attempt=int(p.read_text())+1 if p.exists() else 1\np.write_text(str(attempt))\n"
        "print('HTTPError: Response code 500 (Internal Server Error)')\n"
        "sys.exit(0 if attempt==int(sys.argv[2]) else 7)\n"
    )
    assert build([sys.executable, str(child), str(counter), "2"], pause=lambda _: None) == 0
    assert counter.read_text() == "2"
    counter.unlink()
    assert build([sys.executable, str(child), str(counter), "3"], pause=lambda _: None) == 7
    assert counter.read_text() == "2"


def test_integrity_and_non_transient_failures_do_not_qualify_for_a_retry():
    assert transient_download("HTTPError: Response code 503 (Service Unavailable)")
    for text in (
        "HTTPError: Response code 404 (Not Found)",
        "HTTPError: Response code 500\nchecksum mismatch",
        "HTTPError: Response code 502\ninvalid signature",
        "TypeScript compilation failed",
        "HTTPError: Response code 504\nENOSPC",
    ):
        assert not transient_download(text)
