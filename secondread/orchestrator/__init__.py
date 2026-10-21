"""Orchestrator: classification, planning, parallel review, reactions, conflict rules, report.

Agents come from an ``AgentRegistry``; nothing here imports a concrete agent.
"""

from secondread.orchestrator.assemble import build_report, count_by_severity, verdict_line
from secondread.orchestrator.classify import Classification, classify, heuristic_profile
from secondread.orchestrator.conflicts import (
    Decision,
    Resolution,
    discard_fact_rebuttals_on_verified,
    downgrade_unsourced_rebuttals,
    drop_copy_edits_on_flagged_spans,
    ensure_rebuttal_findings,
    merge_same_span_findings,
    rank_findings,
    rank_rebuttals,
    resolve_conflicts,
)
from secondread.orchestrator.orchestrator import Orchestrator
from secondread.orchestrator.planning import default_plan, split_budget, validate_plan
from secondread.orchestrator.progress import STEP_ORDER, STEP_RANGES, ProgressTracker
from secondread.orchestrator.prompts import TAG_CLASSIFY, TAG_PLAN, TAG_RULING
from secondread.orchestrator.registry import AgentRegistry

__all__ = [
    "STEP_ORDER",
    "STEP_RANGES",
    "TAG_CLASSIFY",
    "TAG_PLAN",
    "TAG_RULING",
    "AgentRegistry",
    "Classification",
    "Decision",
    "Orchestrator",
    "ProgressTracker",
    "Resolution",
    "build_report",
    "classify",
    "count_by_severity",
    "default_plan",
    "discard_fact_rebuttals_on_verified",
    "downgrade_unsourced_rebuttals",
    "drop_copy_edits_on_flagged_spans",
    "ensure_rebuttal_findings",
    "heuristic_profile",
    "merge_same_span_findings",
    "rank_findings",
    "rank_rebuttals",
    "resolve_conflicts",
    "split_budget",
    "validate_plan",
    "verdict_line",
]
