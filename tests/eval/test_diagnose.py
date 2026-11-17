"""Miss diagnosis: which stage a missed fact error got through, from a report alone."""

from __future__ import annotations

from eval.diagnose import (
    MissStage,
    diagnose_miss,
    flagged_at_any_level,
    has_fact_check,
    trail_summary,
)
from eval.harness import save_results
from eval.items import report_items
from eval.metrics import score_report
from eval.results import EvalResults, render_misses, run_metrics
from secondread.contracts import (
    Claim,
    ClaimLedger,
    ClaimType,
    Finding,
    Profile,
    Report,
    ResearchAction,
    ResearchStep,
    Severity,
    Verdict,
)
from tests.eval.helpers import TEXT, ev, span, tiny_seeded

WRONG = "Liverpool won the 2019-20 league with 105 points."
OTHER = "The club was founded in 1892."


def _claim(quote: str, cid: str) -> Claim:
    return Claim(id=cid, text=quote, span=span(quote), type=ClaimType.FACTUAL, importance=0.5)


def _finding(severity: Severity, fid: str, quote: str | None = WRONG) -> Finding:
    return Finding.model_validate(
        {
            "id": fid,
            "agent": "factcheck",
            "severity": severity,
            "span": span(quote) if quote else None,
            "message": "fact-checker says so",
        }
    )


def _step(action: ResearchAction, text: str, summary: str = "", iteration: int = 1) -> ResearchStep:
    return ResearchStep(
        agent="factcheck", iteration=iteration, action=action, input=text, summary=summary
    )


def _ledger(wrong_verdict: Verdict | None, *, other_verified: bool = True) -> ClaimLedger:
    """A ledger where the fact-checker ran on another claim, plus (optionally) a
    claim over the planted sentence with the given verdict."""
    ledger = ClaimLedger()
    if other_verified:
        ledger.add_claim(_claim(OTHER, "c_other"))
        ledger.set_verdict("c_other", Verdict.VERIFIED, [ev()])
    if wrong_verdict is not None:
        ledger.add_claim(_claim(WRONG, "c_wrong"))
        if wrong_verdict is not Verdict.UNCHECKED:
            evidence = [ev()] if wrong_verdict in (Verdict.VERIFIED, Verdict.WRONG) else []
            ledger.set_verdict("c_wrong", wrong_verdict, evidence, confidence=0.7, note="a note")
    return ledger


def _report(ledger: ClaimLedger, **sections: object) -> Report:
    return Report.model_validate(
        {
            "document_id": "tiny",
            "profile": Profile.OPINION,
            "verdict_line": "v",
            "ledger": ledger,
            **sections,
        }
    )


def _diagnose(report: Report):
    seeded = tiny_seeded()
    defect = seeded.defect("wrong")
    return diagnose_miss(seeded, report, defect, report_items(report))


# -- one test per stage ----------------------------------------------------------


def test_not_extracted_when_no_claim_covers_the_sentence() -> None:
    diagnosis = _diagnose(_report(_ledger(None)))
    assert diagnosis is not None and diagnosis.stage is MissStage.NOT_EXTRACTED


def test_not_checked_when_the_claim_was_never_researched() -> None:
    diagnosis = _diagnose(_report(_ledger(Verdict.UNCHECKED)))
    assert diagnosis is not None and diagnosis.stage is MissStage.NOT_CHECKED


def test_judged_verified_when_the_false_claim_was_confirmed() -> None:
    diagnosis = _diagnose(_report(_ledger(Verdict.VERIFIED)))
    assert diagnosis is not None and diagnosis.stage is MissStage.JUDGED_VERIFIED
    assert "claim c_wrong verdict verified" in diagnosis.detail


def test_could_not_verify_when_only_a_low_severity_note_exists() -> None:
    report = _report(
        _ledger(Verdict.UNSUPPORTED), unverified=[_finding(Severity.CONSIDER, "f_cnv")]
    )
    diagnosis = _diagnose(report)
    assert diagnosis is not None and diagnosis.stage is MissStage.COULD_NOT_VERIFY


def test_flagged_unsupported_when_called_unsupported_not_wrong() -> None:
    report = _report(
        _ledger(Verdict.UNSUPPORTED), must_fix=[_finding(Severity.UNSUPPORTED, "f_unsup")]
    )
    diagnosis = _diagnose(report)
    assert diagnosis is not None and diagnosis.stage is MissStage.FLAGGED_UNSUPPORTED


def test_wrong_no_finding_when_the_verdict_is_wrong_but_nothing_was_reported() -> None:
    diagnosis = _diagnose(_report(_ledger(Verdict.WRONG)))
    assert diagnosis is not None and diagnosis.stage is MissStage.WRONG_NO_FINDING


def test_span_too_wide_when_a_factual_error_finding_is_a_catch_all() -> None:
    body = TEXT.strip()
    catch_all = Finding.model_validate(
        {
            "id": "f_wide",
            "agent": "factcheck",
            "severity": Severity.FACTUAL_ERROR,
            "span": span(body),
            "message": "something in here is wrong",
        }
    )
    diagnosis = _diagnose(_report(_ledger(None), must_fix=[catch_all]))
    assert diagnosis is not None and diagnosis.stage is MissStage.SPAN_TOO_WIDE


def test_not_flagged_when_researched_unsupported_but_nothing_reported() -> None:
    diagnosis = _diagnose(_report(_ledger(Verdict.UNSUPPORTED)))
    assert diagnosis is not None and diagnosis.stage is MissStage.NOT_FLAGGED


def test_no_diagnosis_without_a_fact_checking_ledger() -> None:
    """The single-prompt baseline keeps no research ledger: nothing to diagnose."""
    report = _report(ClaimLedger())
    assert not has_fact_check(report)
    assert _diagnose(report) is None


def test_a_claim_with_a_catch_all_span_does_not_count_as_covering() -> None:
    ledger = _ledger(None)
    whole = TEXT.strip()
    ledger.add_claim(
        Claim(
            id="c_thesis",
            text=whole,
            span=span(whole),
            type=ClaimType.THESIS,
            importance=1.0,
        )
    )
    diagnosis = _diagnose(_report(ledger))
    assert diagnosis is not None and diagnosis.stage is MissStage.NOT_EXTRACTED


# -- detail ------------------------------------------------------------------------


def test_trail_summary_counts_searches_pages_and_failures() -> None:
    ledger = _ledger(Verdict.UNSUPPORTED)
    for step in (
        _step(ResearchAction.SEARCH, "liverpool 2019-20 points"),
        _step(ResearchAction.FETCH_PAGE, "https://a.example/1", "Fetched: A"),
        _step(ResearchAction.FETCH_PAGE, "https://b.example/2", "Fetch failed."),
        _step(ResearchAction.SEARCH, "premier league 2019-20 final table", iteration=2),
    ):
        ledger.add_research_step("c_wrong", step)
    text = trail_summary(ledger.entries["c_wrong"])
    assert "2 search(es), 2 page(s) fetched (1 failed)" in text
    assert "2 round(s)" in text
    assert "single search" not in text
    assert '"liverpool 2019-20 points"' in text


def test_trail_summary_marks_single_search_claims() -> None:
    ledger = _ledger(Verdict.UNSUPPORTED)
    ledger.add_research_step("c_wrong", _step(ResearchAction.SEARCH, "one query"))
    assert "single search, not deep research" in trail_summary(ledger.entries["c_wrong"])


# -- scoring and aggregation -----------------------------------------------------------


async def test_score_marks_flagged_and_miss_for_fact_defects_only() -> None:
    report = _report(
        _ledger(Verdict.UNSUPPORTED), unverified=[_finding(Severity.CONSIDER, "f_cnv")]
    )
    score = await score_report(tiny_seeded(), report, pipeline="p")
    wrong = next(o for o in score.defects if o.defect_id == "wrong")
    assert not wrong.caught and wrong.flagged
    assert wrong.miss is not None and wrong.miss.stage is MissStage.COULD_NOT_VERIFY
    for other in score.defects:
        if other.type.value in {"weak_argument", "borrowed_sentence", "grammar"}:
            assert other.miss is None and not other.flagged


async def test_caught_defect_has_no_miss_and_is_flagged() -> None:
    report = _report(_ledger(Verdict.WRONG), must_fix=[_finding(Severity.FACTUAL_ERROR, "f_w")])
    score = await score_report(tiny_seeded(), report, pipeline="p")
    wrong = next(o for o in score.defects if o.defect_id == "wrong")
    assert wrong.caught and wrong.flagged and wrong.miss is None


async def test_flagged_at_any_level_counts_could_not_verify() -> None:
    report = _report(
        _ledger(Verdict.UNSUPPORTED), unverified=[_finding(Severity.CONSIDER, "f_cnv")]
    )
    seeded = tiny_seeded()
    assert flagged_at_any_level(report_items(report), seeded.defect("wrong"))
    assert not flagged_at_any_level(report_items(_report(_ledger(None))), seeded.defect("wrong"))


async def test_metric_and_report_text(tmp_path) -> None:
    flagged = _report(
        _ledger(Verdict.UNSUPPORTED), unverified=[_finding(Severity.CONSIDER, "f_cnv")]
    )
    silent = _report(_ledger(Verdict.VERIFIED))
    scores = [
        await score_report(tiny_seeded(), flagged, pipeline="full", repeat=0),
        await score_report(tiny_seeded(), silent, pipeline="full", repeat=1),
    ]
    metrics = run_metrics(scores[:1])
    assert metrics["recall.wrong_fact"] == 0.0
    assert metrics["recall.wrong_fact_flagged"] == 1.0
    assert run_metrics(scores[1:])["recall.wrong_fact_flagged"] == 0.0

    results = EvalResults(
        pipelines=["full"], doc_ids=["tiny"], repeats=2, judged=False, scores=scores
    )
    counts = results.miss_stage_counts()["full"]
    assert counts[MissStage.COULD_NOT_VERIFY.value] == 1
    assert counts[MissStage.JUDGED_VERIFIED.value] >= 1
    text = render_misses(results)
    assert "Why fact errors were missed" in text
    assert "tiny:wrong (wrong_fact) r0: could_not_verify" in text
    assert "still flagged the sentence" in text

    _json, md = save_results(results, tmp_path)
    assert "Why fact errors were missed" in md.read_text(encoding="utf-8")


def test_render_misses_is_empty_without_diagnoses() -> None:
    results = EvalResults(pipelines=["p"], doc_ids=[], repeats=1, judged=False, scores=[])
    assert render_misses(results) == ""
