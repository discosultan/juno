import base64
from uuid import uuid4


def short_uuid4() -> str:
    uuid_bytes = uuid4().bytes
    uuid_bytes_b64 = base64.urlsafe_b64encode(uuid_bytes)
    uuid_b64 = uuid_bytes_b64.decode("ascii")
    return uuid_b64[:-2]  # Remove '==' suffix from the end.
