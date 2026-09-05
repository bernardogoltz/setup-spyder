---
name: code-review
description: >
  Reviews the current git diff or open PR against setup-spyder invariants.
  Use when the user asks to review changes, look over a diff, check a PR,
  or do a pre-commit / pre-PR pass.
context: fork
agent: code-review
background: false
allowed-tools: Read Grep Glob Bash(git *) Bash(gh *)
---

Review the current changes in this repository.

1. If `$ARGUMENTS` names a PR, files, or a commit range, review that.
   Otherwise review the open PR on this branch, or `main...HEAD`, or the
   working tree — whichever has a diff.
2. Follow the `code-review` subagent checklist (late Spyder imports,
   isolated config, pytest stubs, cli.py style, no generated fixture
   files in git).
3. Return the review report. Do not edit files.
