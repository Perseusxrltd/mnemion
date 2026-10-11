"""Public service-update trust anchor. Rotation needs an authenticated transition."""

import base64

SERVICE_UPDATE_PUBLIC_KEY = base64.b64decode(
    "DtWUIiycMAtlUxJUqpQPhukJs8cNPfE2cImuB6l4aw0=", validate=True
)
