# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue. Use GitHub's
private vulnerability reporting: open the repository's **Security** tab and
choose **Report a vulnerability**
(<https://github.com/sbanthia92/second-read/security/advisories/new>). If that
is unavailable, open an issue asking for a private channel, without details of
the problem.

Include what you found, how to reproduce it, and the version
(`pip show second-read`). You can expect an acknowledgement within a week.

## Scope

Second Read runs locally and handles API keys and untrusted text, so these are
the areas that matter most:

- **Key exposure.** Anything that could put an API key in a log, an error
  message, a report or a tool result.
- **Prompt injection.** A document or fetched web page that makes the tool
  follow its instructions, leak data, or mark a claim verified without evidence.
- **Server-side request forgery.** Any way to make the page fetcher reach a
  private, local or otherwise non-public address.
- **Output injection.** Untrusted text that escapes the report renderers
  (markdown, HTML, plain text).

How these are handled today is described in `ARCHITECTURE.md`, under "Trust
boundaries and security".

## Supported versions

Only the latest release on PyPI receives fixes.
