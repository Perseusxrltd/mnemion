"""Legacy local storage with the vendor product-analytics component disabled."""

import chromadb
from chromadb.config import Settings
from chromadb.telemetry.product import ProductTelemetryClient, ProductTelemetryEvent
from overrides import override


class DisabledTelemetry(ProductTelemetryClient):
    """Discard events without reading a vendor identifier or creating a sender."""

    @override
    def capture(self, event: ProductTelemetryEvent) -> None:
        return None


def persistent_client(path):
    # Chroma 0.6's anonymized_telemetry=False still enters the vendor component,
    # reads its persistent user ID and invokes a globally disabled SDK. Select
    # a no-op component explicitly as well, including its older setting alias.
    # Mnemion's optional product analytics have a separate policy and transport.
    component = "mnemion.chroma_client.DisabledTelemetry"
    return chromadb.PersistentClient(
        path=str(path),
        settings=Settings(
            anonymized_telemetry=False,
            chroma_product_telemetry_impl=component,
            chroma_telemetry_impl=component,
        ),
    )
