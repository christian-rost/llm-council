"""Backward-compatibility shim — delegates to providers package."""

from .providers import query_model, query_models_parallel  # noqa: F401
