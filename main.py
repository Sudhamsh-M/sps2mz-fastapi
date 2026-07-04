import uuid
import time
from typing import Dict, List
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

app = FastAPI()

# === 1. CORS CONFIGURATION ===
ALLOWED_CORS_ORIGINS = {
    "https://app-sps2mz.example.com",
    "https://exam.sanand.workers.dev",
}

# === Rate Limiting State ===
rate_limit_buckets: Dict[str, List[float]] = {}
RATE_LIMIT_B = 15
RATE_LIMIT_WINDOW = 10.0

def is_allowed(client_id: str) -> bool:
    now = time.time()
    if client_id not in rate_limit_buckets:
        rate_limit_buckets[client_id] = []
    
    # Filter out timestamps older than 10 seconds
    bucket = [t for t in rate_limit_buckets[client_id] if now - t < RATE_LIMIT_WINDOW]
    
    if len(bucket) >= RATE_LIMIT_B:
        rate_limit_buckets[client_id] = bucket # Keep the cleaned bucket
        return False
        
    bucket.append(now)
    rate_limit_buckets[client_id] = bucket
    return True

# === COMBINED HTTP MIDDLEWARE STACK ===
@app.middleware("http")
async def process_middleware_stack(request: Request, call_next):
    # --- Middleware A: Request Context (Inbound) ---
    request_id = request.headers.get("x-request-id") or request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    
    # Store it in request state so our endpoints can access it
    request.state.request_id = request_id

    # Get the incoming origin to check for CORS permissions
    origin = request.headers.get("origin")

    # --- Middleware B: Handle CORS Preflight (OPTIONS) ---
    # Crucial: Return early for OPTIONS requests and DO NOT count them toward rate limits
    if request.method == "OPTIONS":
        response = Response(status_code=status.HTTP_200_OK)
        if origin in ALLOWED_CORS_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "X-Request-ID, X-Client-Id, Content-Type"
            response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["X-Request-ID"] = request_id
        return response

    # --- Middleware C: Rate Limiting ---
    # If no client ID header is present, assign a random unique string so it 
    # doesn't share a bucket with other clean requests and cause an instant 429 lock
    client_id = request.headers.get("x-client-id") or request.headers.get("X-Client-Id")
    if not client_id:
        client_id = f"anonymous-{uuid.uuid4()}"
    
    if not is_allowed(client_id):
        response = JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"}
        )
        if origin in ALLOWED_CORS_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
        response.headers["X-Request-ID"] = request_id
        return response

    # --- Proceed to Endpoint ---
    response = await call_next(request)

    # --- Outbound Modifications (Context & CORS) ---
    response.headers["X-Request-ID"] = request_id
    
    if origin in ALLOWED_CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
        
    return response

# === Endpoint ===
MY_EMAIL = "24f2002960@ds.study.iitm.ac.in"

@app.get("/ping")
async def ping(request: Request):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        content={
            "email": MY_EMAIL, 
            "request_id": request_id
        }
    )