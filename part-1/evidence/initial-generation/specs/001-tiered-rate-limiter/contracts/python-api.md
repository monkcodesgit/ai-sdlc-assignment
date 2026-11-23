# Python API Contract

Fixed by imports in the locked tests. Package root: `src/ratelimiter/`.

## ratelimiter.errors

```python
class RateLimiterError(Exception): ...
class ConfigError(RateLimiterError): ...
class UnknownTierError(RateLimiterError): ...
class InvalidRequestError(RateLimiterError): ...
class CostExceedsCapacityError(RateLimiterError): ...
```

## ratelimiter.config

```python
@dataclass(frozen=True)
class TierConfig:
    name: str
    capacity: int
    refill_rate: float

DEFAULT_TIERS: dict[str, TierConfig]          # free, pro, enterprise
def load_tiers(raw: object) -> dict[str, TierConfig]            # raises ConfigError
def load_tiers_from_json(path: str | os.PathLike) -> dict[str, TierConfig]  # raises ConfigError
```

## ratelimiter.store

```python
@dataclass
class BucketState:
    tokens: float
    last_refill: float

class InMemoryStore:
    def get(self, key: str) -> BucketState | None
    def put(self, key: str, state: BucketState) -> None
    def __len__(self) -> int
```

Any object with `get`, `put`, `__len__` may be passed as `store=`.

## ratelimiter.limiter

```python
@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset: int

class RateLimiter:
    def __init__(self, tiers: Mapping[str, TierConfig],
                 clock: Callable[[], float] = time.monotonic,
                 store: Store | None = None) -> None
    def check(self, client_id: str, tier: str, cost: int = 1) -> Decision
        # raises InvalidRequestError, UnknownTierError, CostExceedsCapacityError (in that order)
```

Thread-safe: concurrent `check` calls are serialised.

## ratelimiter.app

```python
def create_app(tiers: Mapping[str, TierConfig] | None = None,
               clock: Callable[[], float] | None = None) -> FastAPI
```

Defaults: `DEFAULT_TIERS`, `time.monotonic`. Routes per [http-api.md](http-api.md).

## ratelimiter.main

`app: FastAPI` — built at import from `RATELIMITER_TIERS_FILE` (if set) or defaults; invalid file
raises `ConfigError` (service fails to start).
