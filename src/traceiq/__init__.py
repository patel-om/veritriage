"""TraceIQ - verification intelligence for semiconductor regression debug.

TraceIQ ingests verification artifacts (simulation logs in v1), normalizes
them into strongly-typed data models, runs a deterministic rule engine to
classify the failure, and emits structured JSON plus an engineering-grade
HTML report. An optional AI layer summarizes findings - always grounded in
the deterministic evidence extracted beforehand, never in place of it.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
