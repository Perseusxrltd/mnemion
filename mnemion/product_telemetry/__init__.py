"""Optional product measurements, separate from private workspace diagnostics."""

import json
from importlib.resources import files

CONTRACT = json.loads(files(__package__).joinpath("disclosure.json").read_text())
SCHEMA_VERSION = 1
DISCLOSURE_VERSION = CONTRACT["version"]

# Collection stays unavailable until the collector, disclosure and release gates
# are qualified together. Saving an enabled preference is not that qualification.
COLLECTION_AVAILABLE = CONTRACT["collection_available"]
COLLECTOR_URL: str | None = CONTRACT["destination"]
