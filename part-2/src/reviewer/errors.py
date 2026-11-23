"""Exception hierarchy for the reviewer (INV-001, EVAL-005, NFR-004; Constitution VI)."""

from __future__ import annotations


class ReviewerError(Exception):
    """Base class for reviewer errors.

    Raised directly when the provider rejects a request with a non-service HTTP status
    (for example 400, 404 or 422). That signals an application or configuration defect,
    which must count as a failure, not as a service error (Constitution VI).
    """


class LLMServiceError(ReviewerError):
    """Provider or transport failure (EVAL-005).

    Timeouts, connection errors and HTTP 401/403/408/409/429/5xx/529. The application never
    retries it; the evaluation harness does.
    """


class ModelOutputError(ReviewerError):
    """The model reply contained no JSON object, even after one retry (INV-001)."""


class ConfigurationError(ReviewerError):
    """Required credentials or settings are missing from the environment (NFR-004)."""
