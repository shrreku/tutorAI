# Contributing

## Workflow

1. Fork the repository and create a feature branch.
2. Keep changes scoped and include tests for behavior changes.
3. Run the local quality bar before opening a PR:
   - `cd backend && pytest`
   - `cd backend && python -m ruff check app/ tests/`
   - `cd frontend && npm run lint && npm run test && npm run build`
4. Document user-visible contract changes in `README.md` or the relevant `docs/` file.

## Security and Secrets

- Never commit `.env` files, API keys, tokens, uploaded files, or generated artifacts.
- Use the tracked `.env.example` as the template for new environments.
- If you discover a leaked secret in history, rotate it before opening a PR and note the rotation in the PR description.

## Pull Requests

- Explain the user-facing impact.
- Call out migrations, deploy steps, and any new environment variables.
- Include test evidence for backend and frontend changes.

