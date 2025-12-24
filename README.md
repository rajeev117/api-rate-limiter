# API Rate Limiter (Python)

Token Bucket and Sliding Window rate limiting algorithms implemented in Python, with in-memory and Redis-backed distributed versions. Redis operations use Lua scripting for atomic check+update.

## Features

- **Token Bucket** (in-memory & Redis)
  - Burst capacity with smooth refill
  - Configurable capacity and refill rate
- **Sliding Window** (in-memory & Redis)
  - Accurate sliding window without boundary artifacts
  - Configurable window size and request limit
- **Concurrency & Distribution**
  - Per-key mutex for safe concurrent updates (in-memory)
  - Lua scripts for atomic Redis operations
  - Fail-open/fail-closed modes for Redis outages

## Repository layout

- `rate_limiter/`: library package (in-memory + Redis)
- `examples/`: usage examples for the library
- `app/`: distributed demo service (FastAPI)

## Quick start (Docker demo service)

```bash
docker compose up --build
```

Call the protected endpoint:

```bash
curl -i http://localhost:8000/limited
```

Health:

```bash
curl -s http://localhost:8000/health
```

## Configuration

Environment variables (prefix `RL_`):

- `RL_REDIS_URL` (default: `redis://redis:6379/0`)
- `RL_CAPACITY` (default: `10`) — maximum tokens in the bucket
- `RL_REFILL_RATE_PER_SEC` (default: `5.0`) — tokens added per second
- `RL_KEY_PREFIX` (default: `rl`) — Redis key namespace
- `RL_FAILURE_MODE` (default: `fail_open`) — `fail_open` or `fail_closed`

## API

- `GET /limited`
  - Keyed by client IP (`X-Real-IP` / `X-Forwarded-For` / socket address)
  - On allow: `200` with `X-RateLimit-Tokens-Left`
  - On throttle: `429` with JSON `{ "detail": "too many requests", "retry_after_ms": ... }`

- `GET /health`
  - Returns `{ "status": "ok", "redis": true|false }`

## Library usage

Install deps:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

In-memory token bucket:

```python
from rate_limiter import TokenBucketLimiter, TokenBucketConfig

limiter = TokenBucketLimiter(TokenBucketConfig(capacity=10, refill_rate=2))
result = limiter.check("user-123")
print(result.allowed, result.remaining, result.metadata)
```

In-memory sliding window:

```python
from rate_limiter import SlidingWindowLimiter, SlidingWindowConfig

limiter = SlidingWindowLimiter(SlidingWindowConfig(window_size_ms=60000, max_requests=100))
print(limiter.allow("user-123"))
```

Redis token bucket:

```python
from rate_limiter import RedisTokenBucketLimiter, TokenBucketConfig, RedisConfig

limiter = RedisTokenBucketLimiter(
  TokenBucketConfig(capacity=100, refill_rate=10),
  RedisConfig(host="localhost", port=6379, key_prefix="rate:api:", fail_open=True),
)
print(limiter.check("user-123"))
```

Redis sliding window:

```python
from rate_limiter import RedisSlidingWindowLimiter, SlidingWindowConfig, RedisConfig

limiter = RedisSlidingWindowLimiter(
  SlidingWindowConfig(window_size_ms=60000, max_requests=100),
  RedisConfig(host="localhost", port=6379, key_prefix="rate:window:", fail_open=True),
)
print(limiter.check("user-123"))
```

Run examples:

```bash
python examples/usage_examples.py
```

Run tests:

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Algorithm details (Token Bucket)

State is stored per key (e.g., per client) as a Redis hash:

- `tokens`: current token count (float)
- `ts_ms`: last refill timestamp (ms)

For each request:

1. Compute elapsed time since last refill.
2. Refill `tokens += elapsed * refill_rate` (capped at `capacity`).
3. If `tokens >= requested`, decrement and allow; else deny.

This entire sequence runs in **one Lua script** inside Redis, so concurrent requests from multiple app instances cannot interleave and overspend tokens.

## Scalability strategy

- Run N app instances behind a load balancer; all instances talk to the same Redis (or Redis Cluster).
- Since the service is stateless (except Redis), horizontal scaling is straightforward.
- Use distinct rate-limit keys for different dimensions as needed (user id, api key, route, etc.).

## Failure handling strategies

### Redis unavailable
Two common modes are supported via `RL_FAILURE_MODE`:

- `fail_open` (default): if Redis is down, allow requests (protects availability; sacrifices strict limiting).
- `fail_closed`: if Redis is down, throttle with `429` (protects downstream systems; sacrifices availability).

### Redis latency/timeouts
- The Redis client uses low connect/read timeouts to avoid hanging requests.
- Consider using connection pooling, local Redis replicas, or a regional Redis deployment close to app instances.

### Hot keys
- If many requests share the same key (e.g., one API key), that Redis key becomes hot.
- Mitigations: shard by key design, split by route, or use Redis Cluster to distribute keys.

### Clock skew
- The limiter uses app time (`now_ms`) as input. Large clock skew across nodes can affect refill.
- Mitigations: synchronize clocks (NTP) or use Redis server time in Lua (more complex).

## Local dev (without Docker)

1. Start Redis locally.
2. Install deps:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

3. Run:

```bash
uvicorn app.main:app --reload
```

## Quick load test (concurrency)

This uses only the Python standard library (no extra deps).

From the repo root:

```bash
python scripts/load_test.py --requests 200 --concurrency 25 --single-client
```

To simulate many different clients (varies `X-Real-IP` per request):

```bash
python scripts/load_test.py --requests 500 --concurrency 50 --unique-clients
```
