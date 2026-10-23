"""Exercise real legacy storage outside pytest's upstream telemetry exemption."""

import json
from pathlib import Path
import subprocess
import sys


PROBE = r"""
import json, os, socket, sys
from pathlib import Path
import posthog
from chromadb.telemetry.product import ProductTelemetryClient

root = Path(sys.argv[1])
ProductTelemetryClient.USER_ID_PATH = str(root / 'vendor-id')
os.environ['ANONYMIZED_TELEMETRY'] = 'True'
os.environ['CHROMA_PRODUCT_TELEMETRY_IMPL'] = 'chromadb.telemetry.product.posthog.Posthog'
os.environ['CHROMA_TELEMETRY_IMPL'] = 'chromadb.telemetry.product.posthog.Posthog'
captures, network = [], []
posthog.capture = lambda *args, **kwargs: captures.append(True)
def reject_network(*args, **kwargs):
    network.append(True)
    raise RuntimeError('No network is permitted in this local-storage test')
socket.socket.connect = reject_network
socket.socket.connect_ex = reject_network
assert 'pytest' not in sys.modules

from mnemion.backends.chroma import cached_client
from mnemion.chroma_client import DisabledTelemetry, persistent_client
client = cached_client(str(root / 'legacy'))
settings = client.get_settings()
assert settings.anonymized_telemetry is False
assert isinstance(client._system.instance(ProductTelemetryClient), DisabledTelemetry)
collection = client.get_or_create_collection('private-fixture', embedding_function=None)
collection.add(ids=['private-id'], documents=['PRIVATE_SENTINEL'], embeddings=[[0.1, 0.2, 0.3]])
assert collection.get(ids=['private-id'])['documents'] == ['PRIVATE_SENTINEL']
assert collection.query(query_embeddings=[[0.1, 0.2, 0.3]], n_results=1)['ids'] == [['private-id']]
collection.delete(ids=['private-id'])
assert persistent_client(root / 'legacy').get_collection('private-fixture', embedding_function=None).count() == 0
client.delete_collection('private-fixture')
client._system.stop()
assert not captures and not network
assert not Path(ProductTelemetryClient.USER_ID_PATH).exists()
print(json.dumps({'store_query_delete_reopen': True, 'vendor_calls': len(captures),
                  'network_attempts': len(network), 'persistent_vendor_id_created': False}))
"""


def test_legacy_storage_neither_sends_vendor_events_nor_creates_an_identifier(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", PROBE, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "store_query_delete_reopen": True,
        "vendor_calls": 0,
        "network_attempts": 0,
        "persistent_vendor_id_created": False,
    }
