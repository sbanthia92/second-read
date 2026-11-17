"""A finding on the whole sentence still counts as being about the planted error;
saved reports can be scored again offline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from eval.cli import main
from eval.dataset import SeededDocument, load_dataset
from eval.diagnose import MissStage, diagnose_miss
from eval.fake_pipeline import builtin_pipelines
from eval.harness import load_saved_reports, rescore_reports, run_eval
from eval.items import report_items
from eval.metrics import score_report, span_matches
from eval.results import run_metrics
from eval.textspan import allowed_span_length, sentence_span, spans_match
from secondread.contracts import (
    Claim,
    ClaimLedger,
    ClaimType,
    Finding,
    Profile,
    Report,
    Severity,
    Span,
    Verdict,
)
from tests.eval.helpers import ev

SHORT = "the Danish coach"
LONG_SENTENCE = (
    "In September 2026 the club sacked the Danish coach after a 4-1 defeat to IFK Göteborg, "
    "the same opponents they had beaten to become champions less than a year earlier."
)
TEXT = (
    "# A warning\n\n"
    "Mjällby won the league. " + LONG_SENTENCE + " The rest of the paragraph is "
    "about something else entirely, and goes on for a while so that a span covering all of "
    "it would be a catch-all rather than a sentence.\n"
)


def _span(quote: str, text: str = TEXT) -> Span:
    start = text.index(quote)
    return Span(start=start, end=start + len(quote))


def _seeded() -> SeededDocument:
    return SeededDocument.model_validate(
        {
            "id": "coach",
            "title": "A warning",
            "genre": "football_blog",
            "profile": "opinion",
            "text": TEXT,
            "defects": [
                {
                    "id": "d1",
                    "type": "wrong_fact",
                    "quote": SHORT,
                    "correction": "He is Norwegian.",
                }
            ],
        }
    )


def _report(span: Span | None, severity: Severity = Severity.FACTUAL_ERROR) -> Report:
    finding = Finding.model_validate(
        {
            "id": "f1",
            "agent": "factcheck",
            "severity": severity,
            "span": span,
            "message": "the coach is not Danish",
            "evidence": [ev()],
        }
    )
    return Report.model_validate(
        {
            "document_id": "coach",
            "profile": Profile.OPINION,
            "verdict_line": "v",
            "ledger": ClaimLedger(),
            "must_fix": [finding],
        }
    )


# -- the rule -------------------------------------------------------------------------


def test_sentence_span_finds_the_sentence_around_a_span() -> None:
    text = 'One here. Two has a phrase in it. He said "no." Then left.\nNew line here.'
    got = sentence_span(text, _span("phrase", text))
    assert got.text_of(text) == "Two has a phrase in it."
    assert sentence_span(text, _span("Then", text)).text_of(text) == "Then left."
    assert sentence_span(text, _span("New line", text)).text_of(text) == "New line here."
    assert sentence_span(text, _span("One", text)).text_of(text) == "One here."


def test_a_span_crossing_a_break_gets_the_whole_stretch() -> None:
    text = "First. Second. Third."
    assert sentence_span(text, _span("First. Second", text)).text_of(text) == "First. Second."


def test_limit_grows_to_the_sentence_but_not_to_the_paragraph() -> None:
    defect = _span(SHORT)
    sentence = sentence_span(TEXT, defect)
    assert allowed_span_length(defect) == max(4 * len(SHORT), len(SHORT) + 80)
    assert allowed_span_length(defect, sentence) >= len(LONG_SENTENCE)
    assert spans_match(sentence, defect, sentence)
    paragraph = Span(start=_span("Mjällby won").start, end=len(TEXT))
    assert not spans_match(paragraph, defect, sentence)
    assert not spans_match(Span(start=0, end=len(TEXT)), defect, sentence)


def test_without_a_sentence_the_old_rule_applies() -> None:
    defect = _span(SHORT)
    sentence = sentence_span(TEXT, defect)
    assert not span_matches(sentence, defect)  # too wide for the phrase alone
    assert span_matches(sentence, defect, sentence)


def test_loaded_defects_know_their_sentence() -> None:
    defect = _seeded().defect("d1")
    assert defect.sentence is not None
    assert defect.sentence.text_of(TEXT) == LONG_SENTENCE


def test_the_real_dataset_gives_every_defect_a_sentence_that_contains_it() -> None:
    for doc in load_dataset():
        for defect in doc.defects:
            sentence = defect.sentence
            assert sentence is not None, f"{doc.id}:{defect.id}"
            assert sentence.start <= defect.located.start < sentence.end, f"{doc.id}:{defect.id}"


# -- scoring --------------------------------------------------------------------------


async def test_a_factual_error_on_the_whole_sentence_catches_the_planted_phrase() -> None:
    seeded = _seeded()
    sentence = sentence_span(TEXT, seeded.defect("d1").located)
    score = await score_report(seeded, _report(sentence), pipeline="p")
    assert score.defects[0].caught


async def test_a_finding_on_the_whole_paragraph_still_does_not_count() -> None:
    seeded = _seeded()
    paragraph = Span(start=_span("Mjällby won").start, end=len(TEXT))
    score = await score_report(seeded, _report(paragraph), pipeline="p")
    assert not score.defects[0].caught


# -- diagnosis -------------------------------------------------------------------------


def test_a_claim_covering_the_whole_sentence_counts_as_extracted() -> None:
    seeded = _seeded()
    sentence = sentence_span(TEXT, seeded.defect("d1").located)
    ledger = ClaimLedger()
    ledger.add_claim(
        Claim(
            id="c1",
            text=sentence.text_of(TEXT),
            span=sentence,
            type=ClaimType.FACTUAL,
            importance=0.5,
        )
    )
    ledger.set_verdict("c1", Verdict.VERIFIED, [ev()])
    report = Report.model_validate(
        {
            "document_id": "coach",
            "profile": Profile.OPINION,
            "verdict_line": "v",
            "ledger": ledger,
        }
    )
    diagnosis = diagnose_miss(seeded, report, seeded.defect("d1"), report_items(report))
    assert diagnosis is not None and diagnosis.stage is MissStage.JUDGED_VERIFIED


# -- rescoring saved reports ---------------------------------------------------------------


@pytest.fixture
def two_docs() -> list[SeededDocument]:
    return load_dataset(None, ids=["01-leicester-money", "02-possession"])


async def _saved_run(docs: list[SeededDocument], directory: Path) -> object:
    pipes = builtin_pipelines(docs)
    return await run_eval(
        {"oracle-no-rules": pipes["oracle-no-rules"], "noisy": pipes["noisy"]},
        docs,
        reports_dir=directory,
    )


async def test_rescoring_saved_reports_matches_the_original_scores(
    tmp_path: Path, two_docs: list[SeededDocument]
) -> None:
    original = await _saved_run(two_docs, tmp_path)
    rescored = await rescore_reports(two_docs, tmp_path)
    assert set(rescored.pipelines) == {"oracle-no-rules", "noisy"}  # hyphens in the name
    assert set(rescored.doc_ids) == {d.id for d in two_docs}
    for pipeline in rescored.pipelines:
        before = [s for s in original.scores if s.pipeline == pipeline]  # type: ignore[attr-defined]
        after = [s for s in rescored.scores if s.pipeline == pipeline]
        assert run_metrics(after)["recall.overall"] == run_metrics(before)["recall.overall"]
    assert not rescored.judged


async def test_other_files_in_the_reports_folder_are_skipped(
    tmp_path: Path, two_docs: list[SeededDocument]
) -> None:
    await _saved_run(two_docs, tmp_path)
    (tmp_path / "notes.json").write_text("{}", encoding="utf-8")
    (tmp_path / "oracle-unknown-doc-r0.json").write_text("{}", encoding="utf-8")
    assert len(load_saved_reports(two_docs, tmp_path)) == 4  # 2 pipelines x 2 documents


def test_cli_rescore_prints_the_table(
    tmp_path: Path, two_docs: list[SeededDocument], capsys: pytest.CaptureFixture[str]
) -> None:
    asyncio.run(_saved_run(two_docs, tmp_path))
    assert main(["rescore", str(tmp_path)]) == 0
    out = capsys.readouterr()
    assert "Recall: overall" in out.out and "oracle-no-rules" in out.out
    assert "Rescored offline" in out.err


def test_cli_rescore_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["rescore", str(tmp_path / "missing")]) != 0
    assert main(["rescore", str(tmp_path)]) != 0  # an empty folder
    assert "no such directory" in capsys.readouterr().err
