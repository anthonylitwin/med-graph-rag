# Initial QA Evaluation Runbook

This runbook creates repeatable question-answering experiments for the graph QA
side of MedGraphRAG. It assumes the annotation/evaluation workflow has already
selected an ingestion configuration and that Neo4j has been populated from that
frozen graph-building run.

Run all commands from the repository root in PowerShell:

```powershell
Set-Location C:\Users\antho\dev\med-graph-rag
```

## Evaluation Boundary

QA evaluation is read-only against Neo4j. It asks questions, retrieves graph
evidence, optionally generates answers, scores those answers against a QA gold
set, and records artifacts in DVC and MLflow. It does not change the graph.

The existing file below is a plumbing smoke test only:

```text
eval/questions/qa_eval_v001.json
```

The starter gold set below is traceable to accepted relationship rows from the
reviewed annotation gold set. It is a development set until it has been expanded
and reviewed:

```text
eval/questions/qa_gold_v001.json
```

Do not treat early QA results as protected holdout results. First create a
larger reviewed QA set and split it by PMCID into development and holdout
questions.

## 1. Confirm The Graph Is Ready

Start the local services:

```powershell
docker compose up -d neo4j minio mlflow
docker compose ps
```

Wait for MLflow and MinIO:

```powershell
do {
  Start-Sleep -Seconds 2
  try { $mlflowReady = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/health).StatusCode -eq 200 } catch { $mlflowReady = $false }
} until ($mlflowReady)

do {
  Start-Sleep -Seconds 2
  try { $minioReady = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9000/minio/health/live).StatusCode -eq 200 } catch { $minioReady = $false }
} until ($minioReady)
```

Confirm Neo4j contains graph data:

```powershell
docker compose exec -T neo4j cypher-shell `
  -u neo4j -p medgraphrag-password `
  "MATCH (n) RETURN labels(n) AS labels, count(*) AS count ORDER BY count DESC"

docker compose exec -T neo4j cypher-shell `
  -u neo4j -p medgraphrag-password `
  "MATCH ()-[r]->() RETURN type(r) AS relationship_type, count(*) AS count ORDER BY count DESC"
```

Record the ingestion or annotation run that produced this graph. Use that value
as `GraphRunId` in QA experiments.

## 2. Prepare The Host Session

Set MLflow and artifact storage values for the host process:

```powershell
$env:MLFLOW_TRACKING_URI = "http://127.0.0.1:5000"
$env:MLFLOW_S3_ENDPOINT_URL = "http://127.0.0.1:9000"
$env:AWS_ACCESS_KEY_ID = "medgraphrag"
$env:AWS_SECRET_ACCESS_KEY = "medgraphrag-password"
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:OLLAMA_BASE_URL = "http://localhost:11434"
$env:OLLAMA_TIMEOUT_SECONDS = "600"
```

Only set an OpenAI key if you are running the frontier answerer or the optional
LLM judge:

```powershell
$secureOpenAIKey = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secureOpenAIKey).Password
$env:OPENAI_MODEL = "gpt-5.5"
```

## 3. Define The Repeatable DVC Command

Paste this helper into the QA experiment PowerShell session:

```powershell
$Python = ".\.venv\Scripts\python.exe"
$QaQuestionFile = "eval/questions/qa_eval_v001.json"
$QaMlflowExperiment = "medgraphrag-qa-eval-v001"
$MlflowTrackingUri = if ($env:MLFLOW_TRACKING_URI) { $env:MLFLOW_TRACKING_URI } else { "http://127.0.0.1:5000" }

function Invoke-QAEvaluation {
  param(
    [Parameter(Mandatory)] [string] $RunId,
    [string] $QuestionFile = $QaQuestionFile,
    [string] $Profile = "noop",
    [string] $Answerer = "",
    [string] $Model = "",
    [string] $Retriever = "",
    [string] $GraphRunId = "",
    [string] $GraphSource = "",
    [switch] $SkipAnswer,
    [switch] $EnableJudge,
    [string[]] $AdditionalOverrides = @()
  )

  $overrides = @(
    "experiments/params.yaml:qa_eval.eval_id=$RunId",
    "experiments/params.yaml:qa_eval.question_file=$QuestionFile",
    "experiments/params.yaml:qa_eval.output_root=data/qa/eval_v001",
    "experiments/params.yaml:qa_eval.graph_run_id=$GraphRunId",
    "experiments/params.yaml:qa_eval.graph_source=$GraphSource",
    "experiments/params.yaml:qa_eval.model_profile=$Profile",
    "experiments/params.yaml:qa_eval.max_evidence=12",
    "experiments/params.yaml:qa_eval.skip_answer=$($SkipAnswer.IsPresent.ToString().ToLower())",
    "experiments/params.yaml:qa_eval.fail_fast=true",
    "experiments/params.yaml:qa_eval.llm_judge.enabled=$($EnableJudge.IsPresent.ToString().ToLower())",
    "experiments/params.yaml:qa_eval.mlflow.enabled=true",
    "experiments/params.yaml:qa_eval.mlflow.tracking_uri=$MlflowTrackingUri",
    "experiments/params.yaml:qa_eval.mlflow.experiment=$QaMlflowExperiment",
    "experiments/params.yaml:qa_eval.mlflow.run_name=$RunId",
    "experiments/params.yaml:qa_eval.mlflow.log_artifacts=true"
  )

  if ($Answerer) { $overrides += "experiments/params.yaml:qa_eval.answerer_provider=$Answerer" }
  if ($Model) { $overrides += "experiments/params.yaml:qa_eval.model=$Model" }
  if ($Retriever) { $overrides += "experiments/params.yaml:qa_eval.retriever=$Retriever" }
  $overrides += $AdditionalOverrides

  $dvcArgs = @("-m", "dvc", "exp", "run", "-n", $RunId)
  foreach ($override in $overrides) {
    $dvcArgs += @("-S", $override)
  }
  $dvcArgs += "experiments/dvc.yaml:qa-eval"

  & $Python @dvcArgs
  if ($LASTEXITCODE -ne 0) { throw "QA DVC experiment failed: $RunId" }
}
```

If you change this helper, paste the full function into PowerShell again before
rerunning. PowerShell keeps old function definitions in memory.

## 4. Run The QA Plumbing Smoke Test

This validates DVC, MLflow, artifact writing, and deterministic scoring without
Neo4j or a model call:

```powershell
Invoke-QAEvaluation `
  -RunId "smoke-qa-noop-v001" `
  -QuestionFile "eval/questions/qa_eval_v001.json" `
  -Profile "noop"
```

Confirm the outputs:

```powershell
.\.venv\Scripts\python.exe -m dvc exp show
Get-Content data\qa\eval_v001\smoke-qa-noop-v001\summary.md
Get-Content data\qa\eval_v001\smoke-qa-noop-v001\question_results.csv
```

Open MLflow at `http://localhost:5000` and confirm the run contains QA params,
metrics, and artifacts.

## 5. Review Or Expand The QA Gold Set

Use `eval/questions/qa_gold_v001.json` as the first editable template. Each
question should have:

- a clear biomedical question
- expected facts
- expected entities
- expected relationship types
- expected evidence IDs or chunk IDs
- question type
- development or holdout split
- adjudication status

For professor-facing results, expand the file from reviewed relationships in
`data/annotations/gold_v001/bootstrap_v001_full/gold_relationships.csv`, then
manually review the questions before freezing a holdout split.

## 6. Run Retrieval-Only QA Evaluation

This checks whether Neo4j retrieval finds the expected evidence before testing
answer generation:

```powershell
Invoke-QAEvaluation `
  -RunId "qa-retrieval-noninst-graph-v001" `
  -QuestionFile "eval/questions/qa_gold_v001.json" `
  -Profile "noop" `
  -Answerer "noop" `
  -Retriever "graph" `
  -GraphRunId "fullgold-local-noninst-initial-v001" `
  -GraphSource "frozen local non-instruct ingestion" `
  -SkipAnswer
```

Prioritize `retrieval_recall`, `mean_entity_coverage`, and
`mean_relationship_coverage`. If retrieval is poor, fix graph loading or
retrieval before comparing answer models.

## 7. Run A Deterministic Answer Baseline

This uses graph evidence but composes answers with the deterministic no-op
answerer:

```powershell
Invoke-QAEvaluation `
  -RunId "qa-answer-noop-graph-v001" `
  -QuestionFile "eval/questions/qa_gold_v001.json" `
  -Profile "noop" `
  -Answerer "noop" `
  -Retriever "graph" `
  -GraphRunId "fullgold-local-noninst-initial-v001" `
  -GraphSource "frozen local non-instruct ingestion"
```

Use this run to separate retrieval failures from model-generation failures.

## 8. Run The Frontier QA Reference

Run the stronger reference answerer after retrieval metrics are healthy:

```powershell
Invoke-QAEvaluation `
  -RunId "qa-answer-frontier-graph-v001" `
  -QuestionFile "eval/questions/qa_gold_v001.json" `
  -Profile "frontier" `
  -Model "gpt-5.5" `
  -Retriever "graph" `
  -GraphRunId "fullgold-local-noninst-initial-v001" `
  -GraphSource "frozen local non-instruct ingestion" `
  -EnableJudge
```

The deterministic metrics remain primary. The optional judge writes secondary
review artifacts under `model_calls/llm_judge` and `llm_judge_report.json`.

## 9. Optionally Run Local QA

Only run local QA after retrieval is working and Ollama is healthy:

```powershell
ollama list
```

Then run:

```powershell
Invoke-QAEvaluation `
  -RunId "qa-answer-qwen25-graph-v001" `
  -QuestionFile "eval/questions/qa_gold_v001.json" `
  -Profile "local-non-instruct" `
  -Model "qwen2.5:7b-instruct" `
  -Retriever "graph" `
  -GraphRunId "fullgold-local-noninst-initial-v001" `
  -GraphSource "frozen local non-instruct ingestion"
```

If this times out, keep the retrieval-only and frontier/reference QA results and
defer local answer generation until local-model stability is solved.

## 10. Compare And Diagnose

Compare DVC and MLflow results:

```powershell
.\.venv\Scripts\python.exe -m dvc exp show
.\.venv\Scripts\python.exe -m dvc metrics diff
```

Review these files for each run:

```text
data/qa/eval_v001/<run-id>/summary.md
data/qa/eval_v001/<run-id>/question_results.csv
data/qa/eval_v001/<run-id>/retrieved/
data/qa/eval_v001/<run-id>/answers/
```

Diagnose failures in this order:

- retrieval failure: expected evidence was not retrieved
- graph failure: expected facts were never loaded into Neo4j
- answer failure: evidence was retrieved but the answer missed the expected fact
- support failure: the answer made claims not supported by retrieved evidence
- abstention failure: the system answered when it should have declined, or declined when evidence was present

## End-Of-Run Checklist

- The graph provenance was recorded in `eval_manifest.json`.
- The smoke QA run passed before graph-backed runs.
- Retrieval-only evaluation was reviewed before answer generation.
- Deterministic metrics were used as the primary scores.
- Optional LLM judge output was treated as secondary review only.
- Every formal run has a unique DVC experiment name and QA eval ID.
- Every formal run appears in MLflow with artifacts.
- The gold QA set was reviewed before any holdout claim was made.
