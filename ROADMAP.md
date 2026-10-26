# Roadmap

Features and improvements worth building next, roughly in priority order.
Each item says why it matters, using what the first real reviews and the
evaluation runs showed. Contributions are welcome: open an issue first for
anything large.

## Next: quality

1. **Citations that always support the finding.** In the October 2026
   evaluation, about a third of cited sources were judged not to support the
   finding they were attached to. Check each excerpt against the finding
   before attaching it, and drop or replace the ones that do not hold up.
2. **Steadier results between runs.** Two runs on the same draft can reach
   different verdicts, because search results and model judgments vary.
   Options: re-judge disputed claims a second time and keep only agreed
   verdicts, or cache search results within a review.
3. **Measure false alarms properly.** Re-run the hard evaluation documents
   (31–40) with saved reports and confirm how often a true fact is called
   wrong. The first estimate was inflated by a counting bug that has since
   been fixed.
4. **Catch more unsupported claims.** The evaluation caught 2 of 4 planted
   unsupported claims, where a single prompt caught all 4. Flag specific
   statistics and quotations that no source backs, even when nothing
   contradicts them.
5. **Recognise famous quotations.** The originality check finds near-copies
   through search but missed well-known lines that a model recognises from
   memory (1 of 3, against 3 of 3). Add a check against public-domain texts
   and quotation collections.
6. **Stronger rebuttals.** Judged rebuttal quality was 3.75 out of 5, against
   4.5 for a single prompt. Give the devil's advocate more room on the top
   claims and judge its drafts before reporting them.
7. **PDF sources.** Official reports and papers are often PDFs, which the
   fetcher cannot read today.

## Next: cost and speed

8. **Cheaper reviews.** A review uses about 150,000–180,000 tokens. Try the
   devil's advocate on Sonnet instead of Opus, prompt caching for repeated
   instructions, and fewer deep-research claims on short documents, and check
   each change against the evaluation set.
9. **Cost in the report.** Show the estimated cost of the review on the
   user's key in the report footer.
10. **Faster reviews.** About two minutes today. Run more research in
    parallel and stream partial results as they arrive.

## Next: features

11. **Style guide from the MCP tool.** The command line accepts
    `--style-guide`; the `review_document` tool does not yet.
12. **More profiles.** The design lists two more: a report or analyst-note
    profile (number consistency, source checks) and an essay profile.
13. **Save the report as HTML.** The HTML renderer exists for email; expose it
    as a command-line option.
14. **More providers.** Adapters for OpenAI, Brave Search and Exa are in the
    code but switched off. Enable each one after a real review has run
    through it end to end.

## Later: hosted version

15. **Remote MCP server.** Designed in `DESIGN.md`: add a URL in Claude,
    ChatGPT or Cursor, sign in with Google, add a key once, get the report by
    email. This makes Second Read usable from claude.ai and ChatGPT without
    installing anything. It needs hosting, a job queue, encrypted key storage
    and email delivery.

## Evaluation and distribution

16. **A fuller evaluation.** Run all 40 seeded documents, three times each,
    against the single-prompt baseline, and publish the results table in the
    README.
17. **Evaluation on demand in CI.** A small subset run by hand before
    releases, since every run costs money.
18. **More directory listings.** Second Read is in the official MCP Registry
    (`io.github.sbanthia92/second-read`) and Glama. Other directories, such as
    mcp.directory, are still to do.
