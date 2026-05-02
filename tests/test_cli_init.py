from argparse import Namespace

from mnemion import cli


def test_init_auto_mine_uses_explicit_flag(monkeypatch, tmp_path):
    calls = []
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    home.mkdir()
    (project / "mnemion.yaml").write_text("wing: project\nrooms:\n  - name: general\n")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("MNEMION_ANAKTORON_PATH", str(tmp_path / "anaktoron"))
    monkeypatch.setattr("mnemion.entity_detector.scan_for_detection", lambda *_args, **_kw: [])
    monkeypatch.setattr("mnemion.room_detector_local.detect_rooms_local", lambda **_kw: None)
    monkeypatch.setattr(
        "mnemion.miner.mine",
        lambda **kwargs: calls.append(kwargs),
    )

    cli.cmd_init(
        Namespace(
            dir=str(project),
            yes=False,
            auto_mine=True,
            lang="en,pt-br",
            palace=str(tmp_path / "anaktoron"),
        )
    )

    assert calls
    assert calls[0]["project_dir"] == str(project)
    assert calls[0]["anaktoron_path"] == str(tmp_path / "anaktoron")
