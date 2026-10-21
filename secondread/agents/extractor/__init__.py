"""Claim extractor agent.

Splits a document into thesis, supporting and factual claims with exact spans
and importance scores, returned as ``AddClaim`` ledger updates.
"""

from secondread.agents.extractor.agent import ExtractionOutcome, ExtractorAgent
from secondread.agents.extractor.prompts import TAG_EXTRACT, ExtractedClaim, ExtractionOutput
from secondread.agents.extractor.spans import Located, MatchMethod, TextLocator

__all__ = [
    "TAG_EXTRACT",
    "ExtractedClaim",
    "ExtractionOutcome",
    "ExtractionOutput",
    "ExtractorAgent",
    "Located",
    "MatchMethod",
    "TextLocator",
]
