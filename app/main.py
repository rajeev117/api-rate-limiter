from __future__ import annotations

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse
import redis

from app.limiter import RedisTokenBucket, client_ip_from_headers, is_redis_available, retry_after_header_value
from app.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Distributed Rate Limiter", version="0.1.0")

    redis_client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
        retry_on_timeout=True,
    )

    limiter = RedisTokenBucket(
        redis_client,
        key_prefix=settings.key_prefix,
        capacity=settings.capacity,
        refill_rate_per_sec=settings.refill_rate_per_sec,
    )

    @app.get("/health")
    def health() -> dict:
        try:
            redis_client.ping()
            redis_ok = True
        except Exception:
            redis_ok = False
        return {"status": "ok", "redis": redis_ok}

    @app.get("/limited")
    def limited(
        request: Request,
        response: Response,
        x_forwarded_for: str | None = Header(default=None),
        x_real_ip: str | None = Header(default=None),
    ):
        client_ip = client_ip_from_headers(
            x_forwarded_for,
            x_real_ip,
            fallback=request.client.host if request.client else "unknown",
        )

        try:
            result = limiter.allow(key=client_ip, tokens=1)
        except Exception as exc:
            is_conn, msg = is_redis_available(exc)
            if is_conn and settings.failure_mode.lower() == "fail_closed":
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "rate limited (redis unavailable)",
                        "mode": "fail_closed",
                        "error": msg,
                    },
                )
            # fail_open: allow request through when Redis is down
            return {
                "ok": True,
                "limited": False,
                "mode": "fail_open",
                "note": "redis unavailable; request allowed",
            }

        if not result.allowed:
            headers = {}
            retry_after = retry_after_header_value(result.retry_after_ms)
            if retry_after is not None:
                headers["Retry-After"] = retry_after
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "too many requests",
                    "retry_after_ms": result.retry_after_ms,
                },
                headers=headers,
            )

        response.headers["X-RateLimit-Tokens-Left"] = f"{result.tokens_left:.3f}"
        return {"ok": True, "limited": False, "client": client_ip}

    return app


app = create_app()
