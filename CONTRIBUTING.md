# Contributing to Agent Context Lens

Thanks for helping make coding-agent context easier to inspect.

The most useful contributions are small, reproducible, and grounded in a real
repository layout or false positive.

## Before opening an issue

1. Run the latest version against a minimal repository if possible.
2. Remove secrets, private paths, and proprietary instructions from all output.
3. Search existing issues and
   [Discussions](https://github.com/ciceroyang/agent-context-lens/discussions).
4. Include the finding code, command, operating system, and Python version.

Use a bug report for incorrect behavior. Use the context-path request form when
an instruction, rule, skill, or MCP configuration file is not discovered.

## Development setup

Agent Context Lens supports Python 3.10 and later.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\activate
```

## Make a focused change

- Keep the runtime dependency-free.
- Add or update a focused test for every scanner rule.
- Scan only recognized agent-context and MCP configuration files.
- Keep findings deterministic; a scan must never call a model or the network.
- Preserve JSON and Markdown output compatibility within a minor release.

For a new recognized path, include a minimal fixture in the test and document
the path in the README compatibility table.

## Verify the change

Run the full local checks:

```bash
python -m pytest
agent-context-lens . --fail-under 80
python -m build
```

## Pull requests

Keep pull requests narrow enough to review in one pass. Explain:

- the user-visible problem;
- the minimal reproduction or evidence;
- what changed;
- the commands used to verify it;
- any output or compatibility change.

By participating in this project, you agree to keep examples free of secrets
and private repository content.
