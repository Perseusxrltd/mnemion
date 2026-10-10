"""Check Studio read authentication against synthetic config, in isolation."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--repo", required=True, type=Path)
parser.add_argument("--out", required=True, type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo.resolve()))

with tempfile.TemporaryDirectory(prefix="mnemion-auth-study-") as directory:
    profile = Path(directory)
    (profile / "config.json").write_text(
        json.dumps({"llm": {"backend": "none", "api_key": "SYNTHETIC_STUDY_VALUE"}})
    )
    os.environ.update(
        MNEMION_HOME=str(profile),
        MNEMION_ANAKTORON_PATH=str(profile / "anaktoron"),
        MNEMION_STUDIO_TOKEN="synthetic-studio-token",
        ANONYMIZED_TELEMETRY="False",
    )

    # Published v3.6.0 lacks MNEMION_HOME support. Override only config path
    # construction so importing it cannot touch the real user profile.
    import mnemion.config as config

    OriginalConfig = config.MnemionConfig

    class IsolatedConfig(OriginalConfig):
        def __init__(self, config_dir=None):
            super().__init__(config_dir=str(profile))

    config.MnemionConfig = IsolatedConfig
    import mnemion.knowledge_graph as graph

    graph.DEFAULT_KG_PATH = str(profile / "knowledge_graph.sqlite3")
    from fastapi.testclient import TestClient
    from studio.backend.main import app

    with TestClient(app) as client:
        anonymous = client.get("/api/config")
        authenticated = client.get(
            "/api/config", headers={"x-mnemion-studio-token": "synthetic-studio-token"}
        )

    result = {
        "repo": args.repo.name,
        "configured_token": True,
        "anonymous_read_status": anonymous.status_code,
        "anonymous_response_contains_synthetic_provider_key": "SYNTHETIC_STUDY_VALUE"
        in anonymous.text,
        "authenticated_read_status": authenticated.status_code,
        "authenticated_response_contains_synthetic_provider_key": "SYNTHETIC_STUDY_VALUE"
        in authenticated.text,
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
