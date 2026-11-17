"""Locate a model-quoted string in the original text.

Models often change whitespace, quote marks, dashes or case when quoting. The
locator tries an exact match first, then a normalised match whose offsets are
mapped back to the original text, so the returned span always slices the
original.
"""

from __future__ import annotations

import re

from secondread.contracts import Span

SPAN_SLACK_CHARS = 80
SPAN_MAX_FACTOR = 4
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\"')\]]*\s+|\n+")

_CHAR_MAP = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    " ": " ",
}


def _normalise(text: str) -> tuple[str, list[int]]:
    """Lower-case, map typographic characters and collapse whitespace.

    Returns the normalised string and, for each of its characters, the index
    of the original character it came from.
    """
    out: list[str] = []
    index: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        ch = _CHAR_MAP.get(ch, ch)
        if ch.isspace():
            if prev_space or not out:
                continue
            out.append(" ")
            index.append(i)
            prev_space = True
            continue
        prev_space = False
        out.append(ch.lower())
        index.append(i)
    if out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


def locate_quote(text: str, quote: str) -> Span | None:
    """Span of the first occurrence of ``quote`` in ``text``, or None."""
    quote = quote.strip()
    if not quote:
        return None
    start = text.find(quote)
    if start != -1:
        return Span(start=start, end=start + len(quote))
    norm_text, index = _normalise(text)
    norm_quote, _ = _normalise(quote)
    for candidate in (norm_quote, norm_quote.strip(" .\"'")):
        if not candidate:
            continue
        pos = norm_text.find(candidate)
        if pos != -1:
            return Span(start=index[pos], end=index[pos + len(candidate) - 1] + 1)
    return None


def sentence_span(text: str, span: Span) -> Span:
    """The sentence (or line) that contains ``span``.

    Sentences end at ``.``, ``!`` or ``?`` followed by whitespace, or at a line
    break. A span that crosses a break gets the whole stretch it covers.
    """
    start, end = 0, len(text)
    for match in _SENTENCE_BREAK.finditer(text):
        if match.end() <= span.start:
            start = match.end()
        elif match.start() >= span.end:
            end = match.start()
            break
    return Span(start=start, end=end)


def allowed_span_length(defect: Span, sentence: Span | None = None) -> int:
    """The longest finding or claim span that still counts as being about ``defect``.

    A planted error is often a short phrase inside a long sentence ("the Danish
    coach"), and the natural place to flag it is the whole sentence. So the limit
    is the larger of a multiple of the defect's own length and the length of its
    sentence, each with some slack. Whole paragraphs and documents stay too wide.
    """
    size = defect.end - defect.start
    limit = max(SPAN_MAX_FACTOR * size, size + SPAN_SLACK_CHARS)
    if sentence is not None:
        limit = max(limit, (sentence.end - sentence.start) + SPAN_SLACK_CHARS)
    return limit


def spans_match(item: Span, defect: Span, sentence: Span | None = None) -> bool:
    """Overlap by one character or more, and ``item`` is not a catch-all."""
    return item.overlaps(defect) and item.end - item.start <= allowed_span_length(defect, sentence)
