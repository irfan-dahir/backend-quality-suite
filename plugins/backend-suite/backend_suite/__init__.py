"""Portable core of the AI design suite: language-agnostic engines plus the
language adapters that fill their stack seams.

Nothing in here may name a project, a path, or a framework. Project specifics
come from .backend-suite/ in the consuming repo; language specifics come from
backend_suite/adapters/. This package is laid out to match its destination —
plugins/backend-suite/{engine,adapters} in irfan-dahir/ai-backend-suite — so
Phase 1 is a git mv rather than a rewrite.
"""
