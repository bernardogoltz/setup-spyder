---
name: pull-request
description: >
  Opens or updates a GitHub pull request for the current branch. Use only
  when the user asks to open, create, or update a PR.
disable-model-invocation: true
context: fork
agent: pull-request
background: false
allowed-tools: Read Grep Glob Bash(git *) Bash(gh *) Bash(uv run pytest *)
---

Open or update a pull request for the current work.

Arguments from the user (title, extra test-plan items, or "draft"):
$ARGUMENTS

Follow the `pull-request` subagent workflow: do not commit unless the
user asked, never push `main`, never force-push, run `uv run pytest -v`
before opening, then `gh pr create` (or push to the existing PR). Return
the PR URL.
