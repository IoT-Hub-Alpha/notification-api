import jwt
from datetime import datetime, timedelta, timezone

key = r"thisisanunsecurekey"

payload = {
    "user_id": 1,
    "email": "test@example.com",
    "roles": ["admin"],
    "permissions": ["read", "write"],
    "exp": datetime.now(timezone.utc) + timedelta(hours=10),
}

token = jwt.encode(payload, key, algorithm="HS256")
print(token)

decoded = jwt.decode(token, key, algorithms=["HS256"])
print(decoded)
