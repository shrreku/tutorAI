# StudyAgent Harness

This directory is the GitHub-ready scaffold for the open-source harness and
agentic pipelines repository.

It is intentionally separate from the production platform boundary. The harness
repo owns offline evaluation, benchmark workflows, harness runners, and local
agentic experimentation. Production runtime, billing, auth, storage, tracing,
and deploy automation stay in the platform repo.

## License

The harness repo should be published under Apache 2.0.

## Current Layout

- `scripts/` for harness runners and benchmark workflows
- `.github/workflows/` for the harness CI baseline
- `requirements.txt` for the harness runtime dependency set
- future harness modules, eval datasets, and experiment helpers

## Publishing Plan

To publish this as a separate GitHub repository:

1. copy this `research/` tree into a new repo root
2. rename the repo to something like `studyagent-harness`
3. keep the production repo on its own license and deploy history
4. push the new repo to GitHub and wire its CI independently
