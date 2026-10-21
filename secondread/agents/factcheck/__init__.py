"""Fact-checker agent.

``FactCheckAgent`` implements ``Agent`` (name ``factcheck``), ``Rechecker``
and ``Debater``. Prompt tags, all ``ModelTier.MID``: ``factcheck.queries``,
``factcheck.assess``, ``factcheck.judge``, ``factcheck.debate`` (see
``prompts.py``).
"""

from secondread.agents.factcheck.agent import FactCheckAgent
from secondread.agents.factcheck.prompts import TAG_ASSESS, TAG_DEBATE, TAG_JUDGE, TAG_QUERIES

__all__ = ["TAG_ASSESS", "TAG_DEBATE", "TAG_JUDGE", "TAG_QUERIES", "FactCheckAgent"]
