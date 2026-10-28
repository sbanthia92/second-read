# Architecture

How Second Read is built, why it is built that way, and what each choice costs.
This describes the code as it is today. `DESIGN.md` is the original design,
including a hosted service that is not built; where the two differ, this file
describes what runs and `DESIGN.md` describes the plan. The last part of this
file is the reference for the shared types in `secondread/contracts/`.

## What it is

A document reviewer that runs on the user's machine with the user's own API
keys. It takes a draft (text or a public URL) and returns one report: facts
checked against retrieved sources, the strongest evidence-backed counter-case,
structure and copy edits, and originality notes. It is reachable two ways:

- an MCP server over stdio with one tool, `review_document`
  (`secondread/mcp_local/`), for Claude Code, Claude Desktop and other local
  MCP clients;
- a command line, `secondread review` (`secondread/cli/`).

Both call the same function, `secondread.pipeline.run_review`. Nothing is
hosted, nothing is stored after a review, and no data goes to the project's
author. Document text goes to the model provider (Anthropic) and claim-derived
search queries go to the search provider (Tavily), both under the user's keys.

## System overview

```
        CLI                      MCP client (Claude Code / Desktop / Cursor)
   secondread review                       │ stdio
        │                                  ▼
        │                       mcp_local.server  (review_document)
        │                          validate · fetch URL · word cap
        └──────────────┬───────────────────┘
                       ▼
              pipeline.run_review ──► Orchestrator ◄── AgentRegistry
                                          │            (built by registry.py
        classify ► extract ► plan         │             from environment keys)
                                          ▼
             ┌────────── parallel review (shared claim ledger snapshot) ──────────┐
             │ fact-check · devil's advocate · copy edit · structure · originality│
             └────────────────────────────────┬───────────────────────────────────┘
                                              ▼
                     reaction round: re-check, then debate (top claims only)
                                              ▼
                      conflict rules (pure functions) ► rank ► Report
                                              ▼
                              markdown · HTML · plain text renderers

   Providers behind three protocols:  LLMClient  ·  SearchClient  ·  Fetcher
   (Anthropic)                        (Tavily)      (SSRF-guarded HTTP)
```

The rule that shapes everything: **agents propose, the orchestrator and plain
code decide.** Agents return findings and ledger updates; they never mutate
shared state. Models propose verdicts, plans and quotes; code validates each
one against the retrieved evidence and the guardrails before it counts.

## Package map

| Path | Responsibility |
| --- | --- |
| `secondread/contracts/` | Pydantic models, Protocols and errors every package codes against. Changing it touches everything. |
| `secondread/pipeline.py` | `run_review`: the single entry point both front ends call. |
| `secondread/orchestrator/` | Classification, planning, parallel dispatch, reaction round, conflict rules, report assembly, progress, key-rejection watch. |
| `secondread/agents/<name>/` | One package per agent: extractor, factcheck, devils_advocate, copyedit, structure, originality. |
| `secondread/providers/` | Adapters: `llm/` (Anthropic, OpenAI), `search/` (Tavily, Brave, Exa), `fetch/` (HTTP with SSRF protection and text extraction). |
| `secondread/registry.py` | Real wiring from environment variables. Offers Anthropic and Tavily only. |
| `secondread/report/` | One format-neutral view model, three renderers (markdown, HTML email, plain text). |
| `secondread/cli/`, `secondread/mcp_local/` | The two entry points. |
| `secondread/testing/` | Fakes for every protocol and sample data; all tests use these. |
| `eval/` | Seeded documents with answer keys, harness, baselines, metrics. |

## How a review runs

`Orchestrator.review` runs one job end to end. Each stage reports a
`ProgressStep` that the MCP server relays as progress notifications.

1. **Classify.** A cheap-tier call picks a profile (`opinion` or `design_doc`)
   unless the caller named one; a heuristic is the fallback if the call fails.
2. **Extract.** The claim extractor splits the document into a thesis,
   supporting claims and checkable factual claims, each with an exact span and
   an importance score, and a `standalone` restatement that can be researched
   out of context. Long documents are chunked. This runs first because
   everything else reads the ledger it fills.
3. **Plan.** A strong-tier call proposes an execution plan: which agents run,
   which claims get deep research, and each claim's budget. `validate_plan`
   checks it in code (allowed agents for the profile, at most 3 research
   iterations per claim, budgets summing within the job) and replaces an
   invalid plan with `default_plan`. Number-heavy documents get more deep
   claims (12 instead of 8).
4. **Review in parallel.** The planned agents run concurrently against one
   read-only ledger snapshot. Their results are applied afterwards in a fixed
   order (`AGENT_ORDER`), so the outcome does not depend on which agent
   finishes first.
5. **React.** If the devil's advocate retrieved evidence that contradicts a
   claim the fact-checker verified, that claim is re-checked once. Then, for
   the top 3 claims by importance where the two still disagree, each side
   answers the other's evidence once and the orchestrator rules.
6. **Resolve.** Pure functions in `orchestrator/conflicts.py` settle what is
   left (see below), then findings are ranked.
7. **Report.** `assemble` builds a `Report`; renderers turn it into markdown
   for the tool result, and HTML or plain text for email.

A job has hard caps: 400,000 tokens, 60 search calls and 600 seconds by
default. Every agent charges one shared `BudgetMeter` for each model, search
and fetch call. Hitting the time limit returns partial results with a note.
When budget runs short, lower-importance claims get a single search or are
marked `unchecked`; the job does not fail.

## The agents

| Agent | Does | Model tier | Notes |
| --- | --- | --- | --- |
| Extractor | Claims with spans and importance | cheap | Asks for verbatim quotes and locates them in code. |
| Fact-checker | Verdict per factual claim, with cited evidence | mid | Bounded research loop per claim; code enforces the evidence rules. |
| Devil's advocate | Strongest opposing case from retrieved counter-evidence | strong | Same bounded loop; opinion and design-doc prompt variants. |
| Copy editor | Line edits that keep the author's voice | cheap | Verbatim quote plus replacement; unlocatable edits are dropped. |
| Structure reviewer | Flow, order, missing sections, gaps | mid | One call over the whole document; long ones reduced to an outline. |
| Originality checker | Near-matches to text found online | none | No model call: sampling, search and similarity are all code. |

Default models: Claude Haiku 4.5 (cheap), Sonnet 5.5 (mid) and Opus 5.5
(strong). Each tier can be overridden with `SECONDREAD_MODEL_CHEAP`, `_MID`
and `_STRONG`.

### The research loop

The fact-checker and the devil's advocate share one idea: a bounded loop per
claim, not a single search. Each iteration plans queries, searches, fetches the
most promising pages, pulls out the passages that match the claim, and has the
model assess each source. The loop then stops, refines the query, or follows a
link to the primary source it found. It ends when a primary source settles the
claim, when two independent sources agree, when the model says more research
will not help, when the budget runs out, or at three iterations.

The fact-checker then makes one judge call that proposes a verdict. **Code
decides whether the verdict stands.** "Verified" or "wrong" needs a primary
source, two independent sources, or one reputable fetched source that nothing
retrieved contradicts. Social and user-generated hosts never count. A claim is
verified only if every checkable part is. When sources exist but do not back
the claim, it is "unsupported" (must fix); when no adequate source was found,
it is reported as "could not verify" at lower severity, because failing to find
a source is not evidence of an error. Before giving up, a claim gets a "second
look" at pages already fetched for the document's other claims, which costs no
search calls. The evidence attached to a finding is limited to the sources the
judge says it relied on.

### Conflict rules

Applied after the reaction round, as pure functions over the ledger that return
a new ledger plus the decisions taken (IDs and reasons only, never document
text):

- a copy edit on a span flagged wrong or unsupported is dropped, and so is one
  on borrowed or quoted text;
- a rebuttal that attacks a verified claim is kept only if it targets the
  interpretation, not the fact;
- findings from two agents on the same span merge into one with both reasons;
- a rebuttal with no retrieved source is downgraded to "consider";
- ranking: factual error > unsupported > strong rebuttal > structure > style >
  consider.

## Trust boundaries and security

The threat model: documents and fetched web pages are written by strangers and
may contain instructions aimed at the reviewer.

- **Untrusted text only in user messages.** Document text, claims, snippets and
  pages go inside delimited blocks (random-nonce markers, or `<untrusted_*>`
  tags with look-alikes neutralised) in user messages, never in system
  prompts. System prompts tell the model to treat the blocks as data.
- **Models cannot act.** Agents have read-only tools: search, fetch, read. A
  malicious page can waste budget but cannot send, write or change anything.
- **Code re-validates model output.** Cited URLs must be ones the loop
  retrieved, quoted excerpts must occur in the retrieved text, verdicts must be
  settled by the evidence, and claim spans must slice the original document.
  Pages that look like they carry injected instructions are skipped.
- **SSRF.** The fetcher refuses non-http(s) schemes, credentials in URLs,
  unusual ports, localhost, numeric-host tricks, and any host that resolves to a
  non-public address (including IPv6 forms embedding IPv4). Every redirect hop
  is re-checked, redirects and body size are capped (counted after
  decompression), and the check repeats at connect time against the vetted IP
  to close the DNS-rebinding gap.
- **Keys.** Read from the environment or a gitignored `.env`. Held in masked
  `Secret` objects, absent from `repr`, logs and error messages. Error
  messages never contain document text either.
- **Output.** Renderers escape all untrusted text and link only http(s) URLs.
- **Rejected keys surface.** `authwatch` records the first provider
  `AuthError` during a job and raises it at the end, so an invalid or
  out-of-credit key produces a clear error instead of an empty "ready" report.

## Failure handling

An agent that raises or reports an error becomes a note in the report
("fact-check unavailable"); the job still returns a report. Provider failures
retry with backoff. Structured-output failures are re-asked once, then raise
`SchemaError`. The one deliberate exception is a rejected key, which fails the
job (above). Progress reporting can never break a review: a failing progress
send is logged and skipped.

## Design decisions and trade-offs

Each entry says what was chosen, why, and what it costs.

### Evidence and trust

**Code decides verdicts; the model proposes them.**
Why: a model can be wrong, manipulated by a page, or simply agreeable. The
evidence rules are deterministic and testable, so "verified" always has a
source behind it. Cost: more code, and rules that can be stricter than a human
reader (a claim with a real but weak source ends up "could not verify").

**Every finding must cite retrieved evidence.**
Why: the point of the tool is checkable claims, not model opinion. Excerpts are
validated against retrieved text so a citation cannot be invented. Cost: the
tool cannot flag what it cannot find a source for, and a retrieved excerpt can
still be on-topic but not supportive (see the first roadmap item).

**"Could not verify" is separate from "unsupported".**
Why: absence of evidence is not an error, and calling it one would make false
alarms the main output. Cost: one more section in the report, and some real
errors land in the lower-severity bucket.

**Part-by-part verification.**
Why: confirming "the club chartered a plane" says nothing about "the next day".
Requiring every material part to be verified stops one confirmed detail from
carrying a whole sentence. Cost: extra judge output and more claims end up
unverified.

### Orchestration

**Hand-written asyncio orchestration, not an agent framework.**
Why: the control flow is the product (plan, parallel review, reaction round,
rules), and a framework would hide it. Typed Pydantic models keep it legible.
Cost: the project owns retry, budgeting and progress code that a framework
would provide.

**Agents never mutate the ledger.**
Why: parallel agents sharing mutable state would race, and results would depend
on completion order. They return `LedgerUpdate`s; the orchestrator applies them
in a fixed order. Cost: a little indirection, and agents cannot see each
other's work until the reaction round.

**A shared claim ledger instead of agents passing text.**
Why: findings are tied to claim IDs and character spans, so conflicts are
detected by span overlap rather than by reading prose. Cost: everything must
carry accurate spans, which drives the quote-and-locate design below.

**Model-written plan, code-checked.**
Why: the model can see that a document is number-heavy or a design doc and skip
or deepen work; code keeps it inside the profile's allowed agents and the job
budget, and falls back to a default plan if it is invalid. Cost: one strong-tier
call per review, and plans vary between runs.

**A reaction round, capped hard.**
Why: the two research agents often disagree about the same claim, and one
re-check plus one debate exchange on the top three claims resolves most of
that. Cost: extra calls and latency. Caps (one re-check per claim, three
debates, three research iterations) keep the cost bounded.

**Conflict rules as pure functions.**
Why: they are easy to test, trace and explain, and they never touch document
text. Cost: fixed rules cannot weigh nuance a human editor would.

### Models and cost

**Three model tiers by task.**
Why: extraction and copy edits need a cheap model; judging evidence needs a
mid one; building the opposing case and ruling on debates need a strong one.
Cost: three model settings to configure, and rebuttal quality could drop if the
strong tier is downgraded (trying a cheaper devil's advocate is on the roadmap,
to be checked against the evaluation set).

**The originality check uses no model.**
Why: sampling, exact-phrase search and similarity scoring are deterministic,
cheap and reproducible. Cost: it finds near-copies online but misses well-known
lines a model would recognise from memory. Findings are labelled heuristic.

**Structured output via tool calls, with one re-ask.**
Why: current Claude models reject a forced `tool_choice`, so the adapter
requests the tool with `auto` plus an instruction, validates against the
Pydantic model, re-asks once, then raises. Numeric fields are left unbounded in
the schema and clamped in code, so a slightly out-of-range reply degrades
instead of failing validation. Cost: occasional extra calls.

**Models quote; code locates.**
Why: models are unreliable at character offsets. The extractor, copy editor and
structure reviewer ask for verbatim quotes and find them in the document with
layered matching (exact, normalised, trimmed, elided). Quotes that cannot be
located are dropped rather than given an invented span. Cost: some valid edits
are lost when a quote does not match.

**Whole review costs real money, and the budgets are the guard.**
A review is about 150,000 to 180,000 tokens and roughly $0.60 to $1.20. Job and
per-claim caps keep a long or hostile document from running up a bill. Cost:
deep research is limited to the most important claims.

### Product shape

**Local and bring-your-own-key, not hosted.**
Why: the project never pays for inference, stores no documents, and needs no
accounts, queue or email, and `DESIGN.md` builds the local engine first so
hosting work waits until review quality is proven. Cost: setup needs `uv` and two API keys, and ChatGPT and claude.ai on
the web cannot connect, because they accept only remote MCP servers. A hosted
service is designed in `DESIGN.md` and listed on the roadmap.

**One public tool, not granular ones.**
Why: exposing `extract_claims` or `find_counterevidence` would hand
orchestration to the client. Cost: users cannot run one stage alone.

**Anthropic and Tavily only.**
Why: they are the pair a real review has run through end to end. OpenAI, Brave
and Exa adapters exist behind the same protocols but are not offered by
`registry.py` until a real review has run through each. Cost: fewer choices
today.

**One report model, three renderers.**
Why: `ReportView` decides section order, grouping, quoting and link safety
once; markdown, HTML and text only format it. Cost: a new section touches the
view and every renderer, which snapshot tests cover.

### Quality and testing

**All tests run offline on fakes.**
Why: tests are fast, free and deterministic. `FakeLLM` keys replies by prompt
tag, so each prompt can be scripted. Tests that call real providers are marked
`live` and skipped by default. Cost: fakes can drift from real provider
behaviour, so live runs and the evaluation still matter.

**A seeded-error evaluation with answer keys.**
Why: quality needs numbers. Each document carries known defects (wrong facts,
unsupported claims, weak arguments, borrowed sentences, grammar errors,
conflicts) and the harness scores recall, precision, citation validity,
rebuttal strength, cost and latency against a single-prompt baseline. Cost:
runs spend real money, so it runs by hand, not on every push.

## Known limits

- **Run-to-run variance.** Search results and model judgments vary, so two runs
  on one draft can reach different verdicts.
- **Citation fit.** A retrieved excerpt can be relevant without supporting the
  finding it is attached to.
- **Unsupported claims.** Specific statistics and quotations that no source
  backs are caught less often than contradicted ones.
- **Sources.** Web pages only; PDFs are not read.
- **Originality.** A heuristic; famous quotations recognised from memory are
  missed.
- **Latency and cost.** About two minutes and 150,000 to 180,000 tokens for a
  700-word article.

`ROADMAP.md` ranks the work to address these.

## Shared contracts reference

The shared types every part of Second Read codes against.

### Layout

| Path | What |
| --- | --- |
| `secondread/contracts/models.py` | Pydantic v2 data models |
| `secondread/contracts/interfaces.py` | Protocols, `ReviewContext`, `BudgetMeter` |
| `secondread/contracts/errors.py` | Exception hierarchy |
| `secondread/testing/fakes.py` | Fakes for every protocol, `make_context` |
| `secondread/testing/samples.py` | Sample documents, ledger, reports |
| `secondread/providers/{llm,search,fetch}/` | Provider adapters |
| `secondread/agents/<name>/` | One package per agent |
| `secondread/report/` | Markdown and HTML rendering |
| `eval/` | Eval harness and dataset |
| `secondread/orchestrator/`, `secondread/pipeline.py` | Planning, conflict rules, `run_review` |
| `secondread/cli/`, `secondread/registry.py` | Real wiring and CLI |
| `secondread/mcp_local/` | stdio MCP server |

Tests mirror the package path under `tests/` (e.g. `tests/agents/extractor/`).

### Data flow

```
Document ──► extractor ──► ClaimLedger ──► plan ──► agents in parallel
                                  ▲                      │ AgentResult
                                  └── orchestrator applies ledger_updates + findings
                                        │ reaction round (recheck, debate)
                                        │ conflict rules, ranking
                                        ▼
                                      Report ──► markdown / HTML
```

### Models (`secondread.contracts`)

- **`Document`**: `id`, `text`, `source_url`, `word_count`. Build with
  `Document.from_text(text)`.
- **`Span`**: half-open `[start, end)` character offsets into `Document.text`.
  `overlaps`, `contains`, `text_of`. Empty spans overlap nothing.
- **`Claim`**: `id`, `text`, `span`, `type` (`ClaimType`: thesis, supporting,
  factual), `importance` 0–1. `text` must equal `span.text_of(doc.text)`.
  `standalone` restates the claim with pronouns and references resolved, so
  it can be researched out of context; `checkable_text` is `standalone or
  text`.
- **`Evidence`**: `url`, `title`, `excerpt`, `retrieved_at`, `is_primary`.
- **`Verdict`**: verified, wrong, unsupported, unchecked. Verified is rejected
  without evidence.
- **`Rebuttal`**: `target_claim_ids` (at least one), `argument`, `evidence`,
  `strength` 1–5, `target` (`RebuttalTarget`: interpretation or fact; used by
  the "rebuttal vs verified claim" rule). No evidence → downgraded to
  `Severity.CONSIDER` by the orchestrator.
- **`Severity`**: `IntEnum`, higher ranks first: factual_error (5) >
  unsupported (4) > strong_rebuttal (3) > structure (2) > style (1) >
  consider (0). `Severity.label` gives the snake_case name.
- **`Finding`**: `agent`, `severity`, optional `span`, `message`, `evidence`,
  `suggestion`, `claim_ids`, `heuristic` (always True for originality),
  `merged_from` (set when the orchestrator merges same-span findings).
- **`AgentName`**: stable agent names (`extractor`, `factcheck`,
  `devils_advocate`, `copyedit`, `structure`, `originality`, `orchestrator`).
- **`ResearchStep`**: one step of a bounded research loop (`iteration` ≤ 3).
- **`DebateRecord`**: positions, ruling, reasoning, final verdict.
- **`LedgerEntry`**: claim, verdict, verdict evidence/confidence/note,
  rebuttals, copy-edit finding IDs, research trail, `rechecked`, `debate`.
- **`ClaimLedger`**: `entries` (by claim ID) and `findings` (by finding ID).
  Helpers: `add_claim`, `set_verdict`, `add_rebuttal`, `add_research_step`,
  `add_finding`, `remove_finding`, `claims(*types)`, `thesis()`,
  `claims_overlapping(span)`, `findings_overlapping(span)`, `apply(update)`,
  `apply_result(result)`. Copy-edit findings are linked to overlapping claims
  automatically.
- **`LedgerUpdate`**: discriminated union `AddClaim | SetVerdict | AddRebuttal
  | AddResearchStep`. **Agents never mutate the ledger**; they return updates
  and the orchestrator applies them, so parallel agents cannot race.
- **`Profile`**: auto, opinion, design_doc. `PROFILE_AGENTS` lists the agents
  each concrete profile may run.
- **`Budget`**: job caps (`max_tokens`, `max_search_calls`, `max_seconds`).
  **`ClaimBudget`**: per-claim caps (`max_iterations` ≤ 3).
  **`ExecutionPlan`**: agents to run, deep-research claim IDs, per-claim
  budgets (`budget_for(claim_id)`).
- **`Usage`**: tokens, search/fetch/LLM calls, seconds; supports `+`.
- **`AgentResult`**: `agent`, `findings`, `ledger_updates`, `usage`, `error`
  (set when the agent degraded instead of failing the job), `notes`
  (non-fatal notices, no document text).
- **`ProgressEvent`**: `step` (usually a `ProgressStep`), `message`,
  `percent` 0–100.
- **`Report`**: verdict line, `counts` (by severity label), must_fix,
  unverified (the fact-checker's "could not confirm" findings: agent
  `factcheck`, severity `CONSIDER`),
  counter_case (rebuttals), should_fix, polish, originality, ledger, usage,
  notes (degradation notices), generated_at.

### Protocols (`secondread.contracts.interfaces`)

- **`LLMClient.complete(messages, *, schema=None, model_tier, tag="",
  max_tokens=None, temperature=None) -> LLMResponse`**. `ModelTier`: cheap,
  mid, strong. With `schema` (a Pydantic model class) the response's `parsed`
  is a validated instance. `tag` names the prompt (e.g. `"factcheck.judge"`);
  fakes key replies on it and it is never sent to the provider.
- **`SearchClient.search(query, *, k=5) -> list[SearchResult]`**.
- **`Fetcher.fetch(url) -> FetchedPage`**; raises `FetchError` or
  `BlockedURLError`.
- **`Agent`**: `name` and `async run(ctx) -> AgentResult`. Must not raise for
  expected failures.
- **`Rechecker.recheck(ctx, claim_id, counter_evidence)`**: fact-checker's one
  re-check per claim.
- **`Debater.respond(ctx, claim_id, opposing_evidence) -> DebatePosition`**:
  one debate response (fact-checker and devil's advocate).
- **`ReviewContext`**: document, profile, ledger (read-only for agents), llm,
  search, fetcher, budget, emit_progress, plan, focus, style_guide, and
  `meter` (a `BudgetMeter` built from `budget`). Agents `charge` the meter for
  every LLM/search/fetch call and stop gracefully when it is exhausted.
- **`ReviewPipeline`**: `(doc, profile, on_progress) -> Awaitable[Report]`,
  implemented by `secondread.pipeline.run_review`.

### Errors (`secondread.contracts.errors`)

`SecondReadError` ← `ProviderError(retryable)` ← `AuthError`,
`RateLimitError`, `SchemaError`; `FetchError` ← `BlockedURLError`;
`BudgetExceeded`; `DocumentTooLong`; `MissingSetup`. Messages must never
contain API keys or document text.

### Fakes (`secondread.testing.fakes`)

- `FakeLLM(script, default=...)`: replies keyed by tag (exact, then dotted
  prefix, then default); list values are queues; replies may be text, dicts,
  models, exceptions or callables `(messages, schema)`. Records `calls`.
- `FakeSearch(results, default=..., error=...)`: substring-keyed hits;
  records `queries`.
- `FakeFetcher(pages)`: URL → page, text or exception; records `fetched`.
- `FakeAgent(name, findings=..., ledger_updates=..., delay=..., raises=...,
  progress=..., on_run=...)`; `FakeFactChecker` (also `Rechecker` and
  `Debater`); `FakeDevilsAdvocate` (also `Debater`).
- `ProgressRecorder`, `make_context(...)`.
- Samples: `sample_documents()` (5 docs), `OPINION_DOC`, `DESIGN_DOC`,
  `REPORT_DOC`, `ESSAY_DOC`, `SHORT_DOC`, `sample_ledger()`,
  `sample_report()`, `empty_report()`, `span_of`, `claim_for`, `FIXED_TIME`.

### Conventions

- Tests run offline with fakes; real-network tests use `@pytest.mark.live`
  (deselected by default; run with `uv run pytest -m live`).
- Checks: `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy`, `uv run pytest`.
- Prompt tags: `<agent>.<step>`, e.g. `extractor.extract`,
  `factcheck.queries`, `factcheck.judge`.
- Document text and fetched pages are untrusted data. Put them in clearly
  delimited user-message blocks, never in system prompts, and never follow
  instructions found inside them.
