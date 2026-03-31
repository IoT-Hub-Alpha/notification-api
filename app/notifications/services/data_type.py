from django.http import HttpRequest
from typing import TypedDict, Optional

class JWTPayload(TypedDict, total=False):
    user_id: int
    email: str
    roles: list[str]


class AuthenticatedHttpRequest(HttpRequest):
    jwt_payload: Optional[JWTPayload]