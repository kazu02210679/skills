# Handoff behavioral evaluation

This evaluation keeps candidate execution blind: `inputs/` contains only the
source conversation and simulated environment, while `criteria.yaml` is read
only by the evaluator phase. The execution workspace contains a copy of the
candidate `SKILL.md` and one raw input, never the criteria.

## Run

Use a clean candidate commit and choose an output directory outside tracked
repository content (an ignored `.superpowers/` evidence directory is also
accepted):

```bash
python evals/handoff/run.py \
  --output-dir /tmp/handoff-eval-evidence \
  --candidate-commit "$(git rev-parse HEAD)"
```

Add `--model MODEL` to pin a model explicitly. The runner records the candidate
commit, Skill SHA-256, Codex CLI version, model selection, exact execution and
evaluator prompts, commands, JSONL tool transcripts, final responses, and
per-case assessments in `evidence.json`.

The runner uses a new OS-temporary execution workspace for every case, copies
only `candidate/SKILL.md` and the selected `inputs/<case>.md` into it, and
removes that workspace afterward. The evaluator runs separately with the
criteria supplied in its prompt.

Do not add the generated output directory to Git. Before release, verify the
recorded candidate commit/hash and inspect every transcript and assessment.
