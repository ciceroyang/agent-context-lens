# Agent Context Lens

> Lighthouse for the context your coding agents actually consume.

[![CI](https://github.com/ciceroyang/agent-context-lens/actions/workflows/ci.yml/badge.svg)](https://github.com/ciceroyang/agent-context-lens/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-00c2ff)](LICENSE)

Coding agents quietly accumulate `AGENTS.md`, Claude instructions, editor
rules, skills, and MCP configuration. That context behaves like a dependency:
it can grow, conflict, break, or expose secrets without a normal code review.

Agent Context Lens maps that dependency locally and gives you a deterministic
scorecard before you add another prompt or call another model.

![Real Agent Context Lens self-scan showing a 100/100 score](docs/assets/terminal-preview.svg)

## Quick start

Install the current release directly from GitHub:

```bash
python -m pip install "git+https://github.com/ciceroyang/agent-context-lens.git"
```

Scan a repository:

```bash
agent-context-lens /path/to/repository
```

Python 3.10 or later is required. The scan reads only recognized context and MCP
configuration files. It makes no network requests or model calls.

## Who this is for

Use Agent Context Lens when you:

- maintain a repository with more than one coding-agent instruction surface;
- add Cursor, Claude, Copilot, Windsurf, skill, or MCP configuration;
- want a deterministic context check before CI or code review;
- need to find duplicate instructions, unsafe MCP configuration, or missing
  verification guidance.

Run it on a real repository, then
[share your score or a missing path](https://github.com/ciceroyang/agent-context-lens/discussions/1).
Please remove secrets, private paths, and proprietary instructions first.

## Why this exists

- **Local by default.** Repository context never leaves your machine.
- **Zero API keys.** The audit is deterministic and makes no model calls.
- **Cross-agent.** It understands common Codex, Claude Code, Cursor, Windsurf,
  Copilot, skill, and MCP paths.
- **CI-ready.** JSON and Markdown output plus a score threshold make drift
  reviewable.
- **Security-aware.** It flags likely inline secrets and broad shell modes in MCP
  configuration.

## Editable development install

Clone the repository and install the development environment:

```bash
git clone https://github.com/ciceroyang/agent-context-lens.git
cd agent-context-lens
python -m pip install -e ".[dev]"
```

## What it scans

Agent Context Lens intentionally avoids reading arbitrary source code. It only
opens recognized agent-context and MCP configuration files:

| Surface | Recognized paths |
|---|---|
| Repository instructions | `AGENTS.md`, nested `AGENTS.md`, `CLAUDE.md` |
| Editor agents | `.cursor/rules/*.mdc`, `.windsurf/rules/*.md` |
| Copilot | `.github/copilot-instructions.md` |
| Portable skills | nested `SKILL.md` files |
| MCP | `.mcp.json`, `mcp.json`, `.cursor/mcp.json`, `.vscode/mcp.json` |

## Reports

Human-readable terminal output is the default:

```bash
agent-context-lens .
```

Create a review artifact:

```bash
agent-context-lens . --format markdown --output agent-context-report.md
```

Feed structured data to another tool:

```bash
agent-context-lens . --format json --output agent-context-report.json
```

Block context regressions in CI:

```bash
agent-context-lens . --fail-under 80
```

The command returns exit status `2` when the score is below the threshold.

## Current checks

- missing repository-level agent instructions;
- approximate context size per file and for the repository;
- repeated substantial instruction lines;
- missing concrete verification or test commands;
- broken local links in Markdown context;
- possible inline secrets in MCP configuration;
- broad shell and dangerous-mode MCP commands.

All findings include stable codes so CI integrations do not have to parse prose.

## Scoring

Every scan starts at 100.

- Critical finding: −25
- Warning: −8
- Notice: −2

The score is deliberately simple. It is a fast review signal, not a claim that
one number can measure agent quality.

## Roadmap

- [ ] Git diff mode for context-cost changes
- [ ] Contradictory instruction detection with explainable evidence
- [ ] SARIF output for GitHub code scanning
- [ ] Provider-specific MCP permission checks
- [ ] Baseline files for gradual CI adoption
- [ ] Tokenizers as optional extras while keeping the default dependency-free

Have a real context failure that this misses? Please open an issue with a minimal
reproduction or use the
[missing context path form](https://github.com/ciceroyang/agent-context-lens/issues/new?template=missing_context_path.yml).
Failure cases will drive the rules.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
agent-context-lens . --fail-under 80
```

Runtime code has no third-party dependencies.

See [CONTRIBUTING.md](CONTRIBUTING.md) for focused changes and verification
requirements. Report vulnerabilities through the private process in
[SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
