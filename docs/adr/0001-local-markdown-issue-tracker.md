---
status: accepted
---

# Track work as local markdown files under `.scratch/`

Specs and tickets are committed markdown in `.scratch/<feature-slug>/`, so an agent can create, claim and close them with plain file edits and the user reads them in the same diff as the code. Considered GitHub Issues but rejected them: sessions run in a cloud container with no `gh` CLI, and issues would not appear in a commit diff.
