"""Say why a planted fact error was not caught, from the report alone.

A miss can happen at several stages of a review, and each calls for a
different fix. Given a missed ``wrong_fact`` or ``unsupported`` defect and the
report, ``diagnose_miss`` reads the claim ledger (claims, verdicts, research
trail) and the findings to name the stage where the error got through:

1. ``not_extracted``: no factual claim covers the sentence.
2. ``not_checked``: a claim covers it but was never researched (claim cap,
   budget, or a provider failure).
3. ``judged_verified``: the false claim was researched and marked verified.
4. ``could_not_verify``: researched, but only a lower-severity "could not
   verify" note was written. The author is still alerted.
5. ``flagged_unsupported``: flagged as unsupported (must fix) but not called
   wrong. The author is still alerted.
6. ``wrong_no_finding``: the verdict is wrong but no matching finding reached
   the report.
7. ``span_too_wide``: a factual-error finding exists but its span is a
   catch-all, so it does not count as matching the sentence.
8. ``not_flagged``: a claim covers it, was researched and is neither verified
   nor wrong, yet nothing was reported.

``flagged_at_any_level`` is true when the author was alerted in any way.
Nothing here calls a model: it only reads the report.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from eval.dataset import SeededDefect, SeededDocument
from eval.items import ItemKind, ReportItem, Role
from eval.textspan import spans_match
from secondread.agents.factcheck.research import (
    DEPTH_DEEP,
    DEPTH_SINGLE,
    FETCH_FAILED_PREFIX,
)
from secondread.contracts import (
    LedgerEntry,
    Report,
    ResearchAction,
    ResearchStep,
    Severity,
    Span,
    Verdict,
)

MAX_QUERIES_SHOWN = 2
MAX_TEXT_CHARS = 90
_FETCH_REASON = re.compile(rf"^{re.escape(FETCH_FAILED_PREFIX)} \((.*?)\)")


class MissStage(StrEnum):
    """Where a planted fact error got through."""

    NOT_EXTRACTED = "not_extracted"
    NOT_CHECKED = "not_checked"
    JUDGED_VERIFIED = "judged_verified"
    COULD_NOT_VERIFY = "could_not_verify"
    FLAGGED_UNSUPPORTED = "flagged_unsupported"
    WRONG_NO_FINDING = "wrong_no_finding"
    SPAN_TOO_WIDE = "span_too_wide"
    NOT_FLAGGED = "not_flagged"


ALERTED_STAGES = frozenset({MissStage.COULD_NOT_VERIFY, MissStage.FLAGGED_UNSUPPORTED})
"""Misses where the author still saw a flag on the sentence."""


class MissDiagnosis(BaseModel):
    """Why one defect was missed: the stage and a short, factual detail."""

    model_config = ConfigDict(extra="forbid")

    stage: MissStage
    detail: str = ""
    quote: str = ""
    """The planted sentence (clipped), so a miss reads without the answer key."""


def _clip(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def has_fact_check(report: Report) -> bool:
    """True if the ledger shows the fact-checker ran (a verdict or research trail).

    Pipelines that keep no research ledger (the single-prompt baseline) cannot
    be diagnosed by stage, so they get no diagnosis rather than a misleading one.
    """
    return any(
        e.verdict is not Verdict.UNCHECKED or e.research_trail
        for e in report.ledger.entries.values()
    )


def _planned_depth(searches: list[ResearchStep]) -> str:
    """ "deep research" or "single search" as recorded on the first search step.

    Empty for reports made before the research loop recorded it."""
    for step in searches:
        for depth in (DEPTH_DEEP, DEPTH_SINGLE):
            if f"({depth})" in step.summary:
                return depth
    return ""


def trail_summary(entry: LedgerEntry) -> str:
    """One line on how a claim was researched.

    Planned depth, searches, pages fetched (with why any failed), sources kept,
    rounds, why research ended, and the first queries tried.
    """
    steps = entry.research_trail
    searches = [s for s in steps if s.action is ResearchAction.SEARCH]
    fetched = [s for s in steps if s.action is ResearchAction.FETCH_PAGE]
    failed = [s for s in fetched if s.summary.startswith(FETCH_FAILED_PREFIX)]
    rounds = max((s.iteration for s in steps), default=0)
    depth = _planned_depth(searches)
    parts = [
        (f"planned {depth}; " if depth else "")
        + f"{len(searches)} search(es), {len(fetched)} page(s) fetched ({len(failed)} failed), "
        f"{len(entry.verdict_evidence)} source(s) kept, {rounds} round(s)"
    ]
    reasons = sorted({m.group(1) for s in failed if (m := _FETCH_REASON.match(s.summary))})
    if reasons:
        parts.append("fetch failures: " + ", ".join(reasons))
    stops = [s for s in steps if s.action is ResearchAction.STOP]
    if stops and stops[-1].summary:
        parts.append(f"ended: {_clip(stops[-1].summary, 110)}")
    queries = [_clip(s.input, 70) for s in searches[:MAX_QUERIES_SHOWN]]
    if queries:
        parts.append("queries: " + " | ".join(f'"{q}"' for q in queries))
    return "; ".join(parts)


def _entry_detail(entry: LedgerEntry) -> str:
    confidence = (
        f", confidence {entry.verdict_confidence:.2f}"
        if entry.verdict_confidence is not None
        else ""
    )
    note = f" Note: {_clip(entry.verdict_note, 140)}" if entry.verdict_note else ""
    return f"verdict {entry.verdict.value}{confidence}. {trail_summary(entry)}.{note}"


def _span_ok(span: Span, defect: SeededDefect) -> bool:
    """The scorer's rule: overlaps the planted error and is not a catch-all."""
    return spans_match(span, defect.located, defect.sentence)


def fact_items_on(items: list[ReportItem], defect: SeededDefect) -> list[ReportItem]:
    """Findings that flag the defect's sentence as a factual problem, at any level."""
    fact_roles = {Role.WRONG, Role.UNSUPPORTED}
    return [
        i
        for i in items
        if i.kind is ItemKind.FINDING
        and i.roles & fact_roles
        and any(_span_ok(s, defect) for s in i.spans)
    ]


def diagnose_miss(
    seeded: SeededDocument, report: Report, defect: SeededDefect, items: list[ReportItem]
) -> MissDiagnosis | None:
    """The stage where a missed fact defect got through, or None if undiagnosable.

    Call this only for a defect that was not caught. Returns None when the
    report has no fact-checker ledger to read.
    """
    found = _classify(report, defect, items)
    if found is None:
        return None
    return found.model_copy(update={"quote": _clip(defect.quote, 80)})


def _classify(
    report: Report, defect: SeededDefect, items: list[ReportItem]
) -> MissDiagnosis | None:
    if not has_fact_check(report):
        return None
    span = defect.located
    entries = [e for e in report.ledger.claims_overlapping(span) if _span_ok(e.claim.span, defect)]
    flags = fact_items_on(items, defect)

    wide = [
        i
        for i in items
        if i.kind is ItemKind.FINDING
        and Role.WRONG in i.roles
        and any(s.overlaps(span) and not _span_ok(s, defect) for s in i.spans)
    ]
    if wide and not entries:
        return MissDiagnosis(
            stage=MissStage.SPAN_TOO_WIDE,
            detail="a factual-error finding overlaps the sentence but its span is a catch-all",
        )
    if not entries:
        return MissDiagnosis(
            stage=MissStage.NOT_EXTRACTED,
            detail="no factual claim in the ledger covers this sentence",
        )

    detail = "; ".join(f"claim {e.claim.id} {_entry_detail(e)}" for e in entries[:2])
    verdicts = {e.verdict for e in entries}
    if Verdict.WRONG in verdicts:
        return MissDiagnosis(
            stage=MissStage.WRONG_NO_FINDING,
            detail=f"verdict wrong but no matching finding in the report; {detail}",
        )
    if flags:
        stage = (
            MissStage.FLAGGED_UNSUPPORTED
            if any(i.severity is Severity.UNSUPPORTED for i in flags)
            else MissStage.COULD_NOT_VERIFY
        )
        return MissDiagnosis(stage=stage, detail=detail)
    if wide:
        return MissDiagnosis(
            stage=MissStage.SPAN_TOO_WIDE,
            detail=f"a factual-error finding overlaps but its span is a catch-all; {detail}",
        )
    if Verdict.VERIFIED in verdicts:
        return MissDiagnosis(stage=MissStage.JUDGED_VERIFIED, detail=detail)
    if verdicts == {Verdict.UNCHECKED}:
        return MissDiagnosis(stage=MissStage.NOT_CHECKED, detail=detail)
    return MissDiagnosis(stage=MissStage.NOT_FLAGGED, detail=detail)


def flagged_at_any_level(items: list[ReportItem], defect: SeededDefect) -> bool:
    """True if the author was alerted to the defect's sentence in any fact finding."""
    return bool(fact_items_on(items, defect))
