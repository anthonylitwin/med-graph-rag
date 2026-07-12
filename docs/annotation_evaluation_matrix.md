# Annotation Evaluation Matrix

This document defines the experiment matrix for comparing frontier extraction,
local instruct extraction, the GLiNER entity-only baseline, and the composed
local non-instruct pipeline.

For the clean-stack setup, exact DVC and MLflow commands, initial profile runs,
artifact checks, and the final non-instruct Neo4j load, see
[`initial_annotation_evaluation_runs.md`](initial_annotation_evaluation_runs.md).

## Evaluation Policy

Tune the non-instruct pipeline only on the development documents. Do not inspect
holdout predictions, errors, or per-type scores until the non-instruct
configuration is frozen. Run the frontier and local instruct comparisons once,
on the final holdout, after local development is complete.

Report entities and relationships separately. Treat any aggregate score as a
secondary summary rather than a replacement for those two result families.

## Gold Split

Use a document-level split so chunks from one paper never appear in both
development and holdout evaluation.

| Split | Documents | Chunks | Entities | Relationships |
| --- | --- | ---: | ---: | ---: |
| Development | `PMC3234107`, `PMC4287928`, `PMC4911828` | 24 | 874 | 481 |
| Final holdout | `PMC3572442`, `PMC4866746` | 19 | 575 | 301 |

Both splits contain the important entity and relationship types. In particular,
both include causation, adverse effects, drug interactions, risk relationships,
and symptom relationships, although some of those types have few examples.

The evaluation runner must support a pinned PMCID split manifest before this
matrix is executed. The current `--limit` option is not a substitute: it selects
chunks by order and does not enforce a durable document boundary.

## Run Matrix

The parameter sweeps are sequential, not a Cartesian product. Carry the winner
from each phase into the next phase.

| Phase | Split | Runs | Configuration |
| --- | --- | ---: | --- |
| Plumbing smoke tests | Small sample | 3 | `noop`, `local-gliner`, and `local-non-instruct` on one or two chunks |
| Development baselines | Development | 2 | `local-gliner` and default `local-non-instruct` |
| Entity threshold sweep | Development | 3 | `entity_threshold`: `0.35`, `0.50`, `0.65` |
| Concept threshold sweep | Development | 3 | `concept_threshold`: `0.78`, `0.86`, `0.94` |
| Relationship threshold sweep | Development | 3 | `relation_threshold`: `0.54`, `0.62`, `0.70` |
| Weight presets | Development | 3 | Balanced, semantic-heavy, and lexical-heavy presets |
| Pair-distance sweep | Development | 3 | `max_pair_distance`: `150`, `300`, `500` |
| Local refinement | Development | 3 | Small variations around the best development configuration |
| Final comparison | Holdout | 4 | Frontier, local instruct, GLiNER ablation, and frozen non-instruct |
| **Scored experiment total** | | **24** | 20 local development runs and 4 final runs; excludes 3 plumbing checks |

The complete workflow therefore contains 27 executions: 3 unscored smoke tests
and 24 scored experiments.

## Weight Presets

| Preset | Semantic | Cue | Proximity | NER confidence |
| --- | ---: | ---: | ---: | ---: |
| Balanced | `0.50` | `0.25` | `0.10` | `0.15` |
| Semantic-heavy | `0.65` | `0.15` | `0.05` | `0.15` |
| Lexical-heavy | `0.30` | `0.45` | `0.10` | `0.15` |

The four weights must be non-negative and have a total greater than zero. The
pipeline normalizes their contribution by the configured total.

## Selection Rules

Use document-macro metrics for model selection so the larger papers do not
dominate tuning.

1. Select `entity_threshold` and `concept_threshold` using document-macro entity
   F1.
2. Select relation thresholds, weights, and pair distance using document-macro
   relationship F1.
3. Break close ties in favor of precision because false graph edges are more
   damaging than missed edges.
4. Review per-type precision, recall, and F1 before accepting a winner.
5. Keep pooled micro metrics as secondary summaries.
6. Do not repeat deterministic local runs unless repeated artifact hashes show
   nondeterminism.

## Final Comparison

After freezing the winning non-instruct configuration, run each of these exactly
once on the untouched holdout:

| Role | Profile | Notes |
| --- | --- | --- |
| Frontier reference | `frontier` | Pin the exact API model and prompt version. |
| Local instruct reference | `local-qwen25` | Pin the exact Ollama model and generation settings. |
| Entity-only ablation | `local-gliner` | Measures the value of normalization and relation scoring over raw NER. |
| Candidate system | `local-non-instruct` | Use the frozen development winner without further adjustment. |

Do not use frontier outputs as labels, terminology, relation prototypes, or
threshold guidance. Do not change the non-instruct configuration after opening
the holdout results.

## Run Naming

Use stable IDs that identify the split, profile, phase, and important changed
parameter. Examples:

```text
dev-local-gliner-baseline-v001
dev-noninst-entity035-v001
dev-noninst-concept086-v001
dev-noninst-relation062-v001
dev-noninst-weights-semantic-v001
holdout-frontier-final-v001
holdout-qwen25-final-v001
holdout-gliner-final-v001
holdout-noninst-final-v001
```

Each run must retain its DVC parameters, DVC lock state, resolved model names,
gold split manifest, metrics, match artifacts, model-call audits, and MLflow run
identifier when MLflow is enabled.

## Execution

Set the profile, run ID, and phase-specific parameters in
`experiments/params.yaml`, then run:

```powershell
.\.venv\Scripts\python.exe -m dvc exp run experiments/dvc.yaml:annotation-eval
.\.venv\Scripts\python.exe -m dvc exp show
```

Do not start the development matrix until the evaluator can select the pinned
development and holdout PMCID manifests directly.
