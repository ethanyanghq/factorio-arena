"""Hands-only Factorio RL environment for LLM agents.

The agent plays Factorio through human primitives (walk, mine, place,
craft, ...) implemented by a Lua mod inside a headless server. See
PLAN.md for the design and REUSE.md for the tooling it builds on.
"""

from importlib.metadata import version

# pyproject.toml is the single source of the version; read it from the
# installed package metadata so the two can never drift apart.
__version__ = version("factorio-arena")
