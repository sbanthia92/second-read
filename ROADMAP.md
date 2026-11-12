# Roadmap

Features and improvements worth building next, roughly in priority order.
Each item says why it matters, using what the first real reviews and the
evaluation runs showed. Contributions are welcome: open an issue first for
anything large.

## Next: reach users

1. **One-click install for Claude Desktop.** Today users edit a JSON file and
   need `uv`. The Claude connectors directory does not list servers that are
   only distributed on PyPI; a local server has to be packaged as an MCPB
   bundle (a `manifest.json`, a privacy-policy URL, tool annotations). The
   privacy section and the tool annotations are done; the bundle and the
   submission are not.
2. **More directory listings.** Second Read is in the official MCP Registry
   (`io.github.sbanthia92/second-read`) and on Glama. Other directories, such
   as mcp.directory, are still to do.

ChatGPT and claude.ai on the web accept only hosted servers, so they need the
remote server under "Later: hosted version".

## Next: quality

3. **Citations that always support the finding.** In the October 2026
   evaluation, about a third of cited sources were judged not to support the
   finding they were attached to. Partly done: the evidence attached to a
   finding is now limited to the sources the judge relied on, and the judge is
   told to leave out any whose excerpt does not back the verdict. Not yet
   measured against the evaluation. Still open: when the model's quote is not
   found verbatim in the page, the excerpt falls back to the page's first
   matching passage, which may not support the finding.
4. **Steadier results between runs.** Two runs on the same draft can reach
   different verdicts, because search results and model judgments vary.
   Options: re-judge disputed claims a second time and keep only agreed
   verdicts, or cache search results within a review. Before building, measure
   how often two judge calls on the same evidence disagree, to see whether the
   model or the search causes most of the variation.
5. **Measure false alarms properly, and record the misses.** Re-run the hard
   evaluation documents (31–40) with saved reports and confirm how often a
   true fact is called wrong. The first estimate was inflated by a counting
   bug that has since been fixed. Also record which planted errors were
   missed and whether each was a careful "could not verify" or missed
   outright; the published result (13 of 19) does not break this down.
6. **Catch more unsupported claims.** The evaluation caught 2 of 4 planted
   unsupported claims, where a single prompt caught all 4. Flag specific
   statistics and quotations that no source backs, even when nothing
   contradicts them.
7. **Recognise famous quotations.** The originality check finds near-copies
   through search but missed well-known lines that a model recognises from
   memory (1 of 3, against 3 of 3). Add a check against public-domain texts
   and quotation collections.
8. **Stronger rebuttals.** Judged rebuttal quality was 3.75 out of 5, against
   4.5 for a single prompt. Give the devil's advocate more room on the top
   claims and judge its drafts before reporting them.
9. **PDF sources.** Official reports and papers are often PDFs, which the
   fetcher cannot read today.

## Next: cost and speed

10. **Cheaper reviews.** A review uses about 150,000–180,000 tokens. Try the
    devil's advocate on Sonnet instead of Opus, prompt caching for repeated
    instructions, and fewer deep-research claims on short documents, and check
    each change against the evaluation set.
11. **Cost in the report.** Show the estimated cost of the review on the
    user's key in the report footer. The footer shows tokens used today.
12. **Faster reviews.** About two minutes today. Run more research in
    parallel and stream partial results as they arrive.

## Next: features

13. **Style guide from the MCP tool.** The command line accepts
    `--style-guide`; the `review_document` tool does not yet.
14. **More profiles.** Two more are planned: a report or analyst-note profile
    (number consistency, source checks) and an essay profile.
15. **Save the report as HTML.** The HTML renderer exists for email; expose it
    as a command-line option.
16. **More providers.** Adapters for OpenAI, Brave Search and Exa are in the
    code but switched off. Enable each one after a real review has run
    through it end to end.

## Later: hosted version

17. **Remote MCP server.** Designed in `ARCHITECTURE.md`: add a URL in Claude,
    ChatGPT or Cursor, sign in with Google, add a key once, get the report by
    email. This makes Second Read usable from claude.ai and ChatGPT without
    installing anything. It needs hosting, a job queue, encrypted key storage
    and email delivery.

## Evaluation

18. **A fuller evaluation.** Run all 40 seeded documents, three times each,
    against the single-prompt baseline, and publish the results table in the
    README.
19. **Evaluation on demand in CI.** A small subset run by hand before
    releases, since every run costs money.

## Shipped

- Published on PyPI (`second-read`), in the official MCP Registry and on
  Glama.
- Tool title and annotations on `review_document`, a Privacy section in the
  README, and `SECURITY.md`.
- `ARCHITECTURE.md` describes the system, its design decisions and trade-offs.
- The README says plainly what its results table compares and what it does
  not show.
