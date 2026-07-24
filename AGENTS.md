# Repository instructions

## Scope

This repository contains a dependency-free Python CLI for auditing coding-agent
context files and MCP configuration.

## Commands

- Run tests: `python -m pytest`
- Run the CLI locally: `PYTHONPATH=src python -m agent_context_lens .`
- Build a package: `python -m build`

## Change rules

- Keep the runtime dependency-free.
- Add or update a focused test for every scanner rule.
- Keep findings deterministic; a scan must never call a model or the network.
- Avoid reading arbitrary source files. Scan only recognized agent-context and MCP
  configuration files.
- Preserve JSON and Markdown output compatibility within a minor release.

## Verification

Before finishing a change, run `python -m pytest` and a self-scan with
`PYTHONPATH=src python -m agent_context_lens . --fail-under 80`.

