# Open pull request behavioral evaluations

Run the blind evaluation harness against a committed candidate:

```bash
python evals/open-pull-request/run.py \
  --output-dir /tmp/open-pull-request-eval-evidence \
  --candidate-commit "$(git rev-parse HEAD)"
```

Use `--model` or `--codex` to select a model or Codex executable. To run only
specific cases, pass a comma-separated filter:

```bash
python evals/open-pull-request/run.py \
  --output-dir /tmp/open-pull-request-eval-evidence \
  --candidate-commit "$(git rev-parse HEAD)" \
  --cases case-01,case-03
```

The candidate phase is blind. Case inputs contain the user request but never
the pass conditions. `criteria.yaml` is read by the harness and supplied only
to the separate evaluator invocation after the candidate has finished.

Each case builds a real throwaway Git repository. Generated `git` and `gh`
wrappers are placed first on `PATH` for the candidate phase and record every
invocation in that case's `calls.log`. Mutating remote commands are refused
unless the fixture explicitly allows them. The no-mutation case is decided
from `calls.log`, not from what the candidate claims in its response. The log
is also included in the evidence manifest.

Fixture-only remote state stays local. `remote.baseAhead` advances the bare
default branch after the local tracking ref was recorded, and `remote.fork`
creates separate origin and upstream repositories. `githubState.remoteUrls`
supplies the public URLs returned by `git remote get-url` without enabling
network access. A string-valued `reviewData` entry is written verbatim so a
case can model malformed JSON.
