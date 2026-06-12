# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue.
Use GitHub's [private vulnerability reporting](https://github.com/napetrov/agent-benchmark/security/advisories/new)
for this repository, or contact the maintainers directly.

When reporting, include:

- a description of the issue and its impact,
- steps to reproduce (a minimal proof of concept is ideal),
- affected versions/commits, and
- any suggested remediation.

We aim to acknowledge reports within a few business days and to keep you
updated as we investigate and remediate.

## Scope and threat model

This is a benchmarking and evaluation harness, not a hardened service. A few
properties are worth calling out for anyone running it:

- **Example execution.** The static benchmark can execute fenced code blocks
  found in documentation to compute `example_pass_rate`. By default this is
  **disabled**, and when enabled it runs in a constrained mode. Do **not** run
  example execution against untrusted documentation outside a sandbox — see
  [`docs/example-execution.md`](docs/example-execution.md).
- **LLM/provider calls.** The LLM track sends prompts (which may include
  retrieved documentation) to third-party model providers. Do not feed secrets
  or confidential material through the pipeline.
- **API keys.** Keys are read from environment variables and are never written
  to artifacts. Keep them out of committed configs and fixtures.

## Supported versions

The project is pre-1.0; only the latest `main` is supported. Fixes land on
`main` and are not backported.
