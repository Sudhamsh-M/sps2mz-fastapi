import uuid
import time
from typing import Callable, Dict, List
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse, JSONResponse

app = FastAPI()

# === CORS (Middleware 2) ===
ALLOWED_CORS_ORIGINS = [
    "https://app-sps2mz.example.com",
    "hhtps://exam.sanand.workers.dev",
    # Add the exam page origin here when you know it, e.g.:
    # "https://exam.example.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id"],
)

# === Rate limiting (Middleware 3) ===
rate_limit_buckets: Dict[str, List[float]] = {}
RATE_LIMIT_B = 15
RATE_LIMIT_WINDOW = 10.0

def is_allowed(client_id: str) -> bool:
    now = time.time()
    if client_id not in rate_limit_buckets:
        rate_limit_buckets[client_id] = []
    bucket = rate_limit_buckets[client_id]
    bucket = [t for t in bucket if now - t < RATE_LIMIT_WINDOW]
    if len(bucket) >= RATE_LIMIT_B:
        return False
    bucket.append(now)
    rate_limit_buckets[client_id] = bucket
    return True

# === Request context middleware (Middleware 1) ===
class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Only process HTTP requests
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        # Create Starlette Request to read headers
        request = StarletteRequest(scope, receive=receive)

        request_id = request.headers.get("x-request-id")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store request_id in state-like dict
        scope["request_id"] = request_id

        # Wrap send to inject X-Request-ID header
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message["headers"]
                ]
                headers.append(("x-request-id", request_id.encode()))
                message["headers"] = headers
            return await send(message)

        return await self.app(scope, receive, send_wrapper)

app.add_middleware(RequestContextMiddleware)

# === Rate limit middleware (Middleware 3) ===
class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request = StarletteRequest(scope, receive=receive)
        client_id = request.headers.get("x-client-id")
        if not client_id:
            client_id = "unknown"

        if not is_allowed(client_id):
            # Return 429 directly
            response = StarletteResponse(
                status_code=429,
                content="Rate limit exceeded",
            )
            return await response(scope, receive, send)

        return await self.app(scope, receive, send)

app.add_middleware(RateLimitMiddleware)

# === Endpoint ===
MY_EMAIL = "24f2002960@ds.study.iitm.ac.in"

@app.get("/ping")
def ping(request: StarletteRequest):
    request_id = request.scope.get("request_id")
    return JSONResponse(
        content={"email": MY_EMAIL, "request_id": request_id}
    )
