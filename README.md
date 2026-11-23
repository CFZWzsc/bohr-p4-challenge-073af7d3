# Runtime contract

Bohrium Playground Period 4 submission — challenge `challenge-073af7d3` (track: `deep-research-literature-review`).

This repository holds the complete skill package for the challenge: the skill
definition, its executable pipeline and all supporting documents. No precomputed
answers, private data or credentials are included.

## Skill

- Name: `research-trend-and-theme-evolution`
- Summary: Use when a dated batch of papers must be turned into a defensible research-frontier picture — yearly output, per-term activity series with lifecycle labels, burst years, representative work per period, theme appearance/growth/decline, open questions and batch-bounded gaps, each claim tied to a locator and an exact quote. Runs offline with the Python standard library only.

## Contents

| File |
|------|
| `SKILL.md` |
| `assets/policy.json` |
| `examples/demo-case/case.json` |
| `examples/quickstart.md` |
| `references/evidence-discipline.md` |
| `references/method.md` |
| `references/task-spec.md` |
| `scripts/run_skill.py` |
| `scripts/sk_entry.py` |
| `README.md` |

## How to run

```bash
python scripts/sk_entry.py --input /input --work /app/work --out /app/output
```

A single deterministic pass reads `/input`, computes the deliverable and writes a
contract-complete `/app/output/result.json` plus the human-readable review files
described in `SKILL.md`. The same input always produces byte-identical output; no
network access is used, and fields the materials cannot support are reported
explicitly instead of being left empty.

## Notes

- Pure Python standard library; no network access required.
- Every claim is anchored to paragraph-level evidence; unknown items are reported
  in `uncertainty` instead of being fabricated.
