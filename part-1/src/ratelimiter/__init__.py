"""Tiered token-bucket rate limiter.

Core modules (errors, config, store, limiter) use only the standard library; the HTTP layer
lives in ``ratelimiter.app`` and is not imported here.
"""

__all__: list[str] = []
