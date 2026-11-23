"""HTTP layer (FastAPI) for the tiered rate limiter."""

import time
from collections.abc import Callable, Mapping
from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from .config import DEFAULT_TIERS, TierConfig
from .errors import CostExceedsCapacityError, InvalidRequestError, UnknownTierError
from .limiter import Decision, RateLimiter


class CheckRequest(BaseModel):
    """Body of ``POST /v1/check``; unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    client_id: Annotated[
        StrictStr, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:@-]+$")
    ]
    tier: Annotated[StrictStr, Field(min_length=1, max_length=32)]
    cost: Annotated[StrictInt, Field(ge=1)] = 1


def _ratelimit_headers(decision: Decision) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(decision.remaining),
        "X-RateLimit-Reset": str(decision.reset),
    }


def _decision_response(decision: Decision) -> JSONResponse:
    headers = _ratelimit_headers(decision)
    if decision.allowed:
        body = {
            "allowed": True,
            "limit": decision.limit,
            "remaining": decision.remaining,
            "retry_after": 0,
            "reset": decision.reset,
        }
        return JSONResponse(status_code=200, content=body, headers=headers)
    headers["Retry-After"] = str(decision.retry_after)
    body = {
        "allowed": False,
        "error": "rate_limited",
        "limit": decision.limit,
        "remaining": decision.remaining,
        "retry_after": decision.retry_after,
        "reset": decision.reset,
    }
    return JSONResponse(status_code=429, content=body, headers=headers)


def _register_error_handlers(app: FastAPI) -> None:
    """Map errors to the HTTP contract; bodies never carry traces, paths or echoed input."""

    @app.exception_handler(UnknownTierError)
    async def _unknown_tier(_request: Request, _exc: UnknownTierError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "unknown_tier"})

    @app.exception_handler(CostExceedsCapacityError)
    async def _cost_too_big(_request: Request, _exc: CostExceedsCapacityError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "cost_exceeds_capacity"})

    @app.exception_handler(InvalidRequestError)
    async def _invalid(_request: Request, _exc: InvalidRequestError) -> JSONResponse:
        detail = [{"type": "value_error", "loc": ["body"], "msg": "invalid request"}]
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(RequestValidationError)
    async def _schema(_request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = [
            {"type": err.get("type"), "loc": list(err.get("loc", ())), "msg": err.get("msg")}
            for err in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(Exception)
    async def _internal(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": "internal_error"})


def create_app(
    tiers: Mapping[str, TierConfig] | None = None,
    clock: Callable[[], float] | None = None,
) -> FastAPI:
    """Build the HTTP app. Defaults: DEFAULT_TIERS and a monotonic clock."""
    limiter = RateLimiter(
        DEFAULT_TIERS if tiers is None else tiers,
        clock=time.monotonic if clock is None else clock,
    )
    app = FastAPI(title="Tiered Rate Limiter")
    _register_error_handlers(app)

    @app.post("/v1/check")
    def check(body: CheckRequest) -> JSONResponse:
        decision = limiter.check(body.client_id, body.tier, body.cost)
        return _decision_response(decision)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
