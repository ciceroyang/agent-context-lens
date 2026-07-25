# Security policy

## Supported versions

Security fixes are provided for the latest release.

| Version | Supported |
|---|---|
| `0.1.x` | Yes |
| Earlier versions | No |

## Report a vulnerability privately

Do not open a public issue for a vulnerability or include real credentials in a
reproduction.

Use GitHub's
[private vulnerability reporting](https://github.com/ciceroyang/agent-context-lens/security/advisories/new)
to describe:

- the affected version and platform;
- the smallest safe reproduction;
- the expected and actual behavior;
- the potential impact;
- any suggested mitigation.

You should receive an acknowledgement within five business days. A confirmed
report will be investigated before public disclosure.

## Scope

Security-relevant reports include:

- reading files outside recognized context paths;
- following symlinks outside the scanned repository;
- leaking file contents through reports;
- false negatives in checks that claim to detect inline secrets or dangerous
  MCP execution modes;
- command execution, network access, or model calls during a scan.

The scanner is a review aid, not a replacement for dedicated secret scanning,
static analysis, or sandboxing.
