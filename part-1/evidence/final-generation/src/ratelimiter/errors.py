"""Exception hierarchy for the rate limiter (standard library only)."""


class RateLimiterError(Exception):
    """Base class for every error raised by the rate limiter."""


class ConfigError(RateLimiterError):
    """A tier configuration (mapping or JSON file) is invalid."""


class UnknownTierError(RateLimiterError):
    """The requested tier is not configured."""


class InvalidRequestError(RateLimiterError):
    """The client id or cost of a request is invalid."""


class CostExceedsCapacityError(RateLimiterError):
    """The request cost is larger than the tier's bucket capacity."""
