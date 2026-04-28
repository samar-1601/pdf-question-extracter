# Repo context for Claude

## What this repo is
An AI-guided learning platform — early-stage startup codebase. Helps learners interpret their test scores, understand error patterns, and get AI-driven study recommendations grounded in tagged question data. Includes an admin dashboard for content operators.

For product scope, target users, and value proposition, see [business.md](./business.md).
For services, data model, and application flows, see [architecture.md](./architecture.md).

## Current state
- Repo is bootstrapped from a starter template (`index.html`, `package.json`, basic README).
- Product surface (learner UI, admin dashboard, API, AI analysis) is **not yet implemented** — see architecture.md for the planned shape.
- Treat any new code as greenfield: pick conventions intentionally rather than matching what's currently in the repo.

## Working preferences
- Frontend stack decisions default to React (user is a frontend expert in React/JS).
- Backend stack is open; if Go is chosen, lean on the user's in-progress Go learning.
- Keep new abstractions minimal until product shape is clearer — avoid premature service splits.
- Don't bloat this file. Put product context in business.md, technical/system context in architecture.md, and link from here.

## When making changes
- New features: confirm whether they fit the learner flow or admin flow (architecture.md sequence diagrams).
- New entities: update the ER diagram in architecture.md.
- New services or data flow changes: update the system diagram in architecture.md.
- Product scope changes: update business.md.

## Things this repo is not
- Not a public/open-source project. Treat as private.
- Not affiliated with any other organization or codebase the user works in — keep all references self-contained to this repo.
