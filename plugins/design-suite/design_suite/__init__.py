"""Portable core of the AI design suite: language-agnostic engines plus the
language adapters that fill their stack seams.

Nothing in here may name a project, a path, or a framework. Project specifics
come from .design-suite/ in the consuming repo; language specifics come from
design_suite/adapters/. This package is laid out to match its destination —
plugins/design-suite/{engine,adapters} in irfan-dahir/ai-design-suite — so
Phase 1 is a git mv rather than a rewrite.
"""
