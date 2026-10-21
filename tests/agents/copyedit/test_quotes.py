from secondread.agents.copyedit import CopyEditAgent
from secondread.agents.copyedit.prompts import SYSTEM_PROMPT
from secondread.agents.copyedit.text import quoted_spans
from secondread.contracts import Document
from secondread.testing.fakes import FakeLLM, make_context

TEXT = (
    "Busby told him, “Keep the flag flyng,” from his bed. The players was tired.\n\n"
    "> Hence to fight and conqer in all your battles is not supreme excellence.\n\n"
    'He said "dont worry" and left.'
)


def test_quoted_spans_cover_quotations_and_block_quotes():
    spans = [s.text_of(TEXT) for s in quoted_spans(TEXT)]
    assert "“Keep the flag flyng,”" in spans
    assert '"dont worry"' in spans
    assert any(s.startswith("> Hence to fight") for s in spans)
    assert not any("players was" in s for s in spans)


async def test_edits_inside_quotations_are_dropped():
    doc = Document.from_text(TEXT)
    llm = FakeLLM(
        {
            "copyedit.edit": {
                "edits": [
                    {"quote": "Keep the flag flyng", "suggestion": "Keep the flag flying"},
                    {"quote": "fight and conqer", "suggestion": "fight and conquer"},
                    {"quote": "dont worry", "suggestion": "don't worry"},
                    {"quote": "The players was tired.", "suggestion": "The players were tired."},
                ]
            }
        }
    )
    result = await CopyEditAgent().run(make_context(doc, llm=llm))
    assert [f.suggestion for f in result.findings] == ["The players were tired."]
    assert "3 copy edit(s) inside quotations were dropped" in result.notes


def test_prompt_forbids_editing_quotations():
    assert "Never edit quotations" in SYSTEM_PROMPT
