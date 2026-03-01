import base64
import json
from slowapi import Limiter
from slowapi.util import get_remote_address


def _get_uid_from_request(request) -> str:
    """
    Extract the Firebase UID from the Authorization bearer token for use as
    the rate limit key. Falls back to IP address for unauthenticated requests.

    The token signature is NOT re-verified here — full verification already
    happens in get_current_user. The UID is only used as a bucketing key.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return get_remote_address(request)
    token = auth.split(" ", 1)[1].strip()
    try:
        segment = token.split(".")[1]
        # Add padding required for base64url decoding
        segment += "=" * (4 - len(segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(segment))
        # Firebase JWTs use "user_id" claim; "sub" is the standard fallback
        uid = str(payload.get("user_id") or payload.get("sub") or "")
        if uid:
            return f"uid:{uid}"
    except Exception:
        pass
    return get_remote_address(request)


limiter = Limiter(key_func=_get_uid_from_request)
