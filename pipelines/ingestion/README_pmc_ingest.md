# PMC Ingestion Pipeline Usage And Testing

This guide covers manual usage and verification for the PMC ingestion and extraction pipeline.
For the full repo runbook, including UI, QA, benchmark ingestion, artifacts, and
algorithm extension points, see `docs/complete_test_run.md`.

The pipeline can:

- Read PMC IDs from CLI arguments or a newline-only text file.
- Fetch PMC BioC JSON from NCBI.
- Write raw JSON, full text, processed chunks, extraction outputs, and a manifest.
- Extract biomedical entities and relationships with OpenAI or local GLiNER + Ollama.
- Load validated graph facts into Neo4j.

## Prerequisites

Create or update `.env` with:

```text
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-5.5
OPENAI_REASONING_EFFORT=medium
MODEL_PROFILE=frontier
LOCAL_MODEL=qwen2.5:7b-instruct
OLLAMA_BASE_URL=http://localhost:11434
EXTRACTOR_ENTITY_MODEL=Ihor/gliner-biomed-small-v1.0
NEO4J_LOCAL_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=medgraphrag-password
```

Install Python dependencies if needed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt
```

For local GLiNER extraction, install optional model dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-local-models.txt
ollama pull qwen2.5:7b-instruct
```

For Neo4j load tests, start Neo4j:

```powershell
docker compose up neo4j
```

## Input Formats

Pass PMC IDs directly:

```powershell
.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py --pmcid PMC3572442 PMC3234107
```

Or use a plain text file with one PMCID per line:

```powershell
.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py --pmcid-file data/source_documents/benchmark_pmcids.txt --limit 2
```

Blank lines and lines starting with `#` are ignored. Markdown tables, CSV, and mixed prose are not accepted by `--pmcid-file`.

## Fast Smoke Test

Use this first. It fetches BioC, parses text, chunks the article, writes artifacts, and updates the manifest. It does not call OpenAI or Neo4j.

```powershell
.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py `
  --pmcid-file data/source_documents/benchmark_pmcids.txt `
  --limit 1 `
  --model-profile noop `
  --skip-load
```

Expected outputs:

```text
data/source_documents/pmc_v001/raw/PMC3572442.json
data/source_documents/pmc_v001/text/PMC3572442.txt
data/source_documents/pmc_v001/processed/PMC3572442.json
data/source_documents/pmc_v001/manifest.csv
```

Check that `manifest.csv` shows `fetch_status=ok`, `extract_status=ok`, `load_status=skipped`, and `status=ok`.

## OpenAI Extraction Test

Run one article without loading Neo4j:

```powershell
.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py `
  --pmcid PMC3572442 `
  --model-profile frontier `
  --skip-load
```

## Local GLiNER + Ollama Extraction Test

Run one article locally without loading Neo4j:

```powershell
.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py `
  --pmcid PMC3572442 `
  --model-profile local-qwen25 `
  --skip-load
```

This uses GLiNER-BioMed for ontology entity candidates and Ollama/Qwen for
relationships among those candidates. The same extraction validator still drops
unsupported entity types, invalid relationship directions, low-confidence facts,
and relationships without evidence.

Inspect:

```text
data/source_documents/pmc_v001/processed/PMC3572442.json
```

The processed JSON should include:

- `run`
- `document`
- `chunks`
- `extractions`
- `entities`
- `relationships`
- `rejected_candidates`

For a successful extraction run, `entities` and `relationships` should contain validated ontology objects unless the model found no supported facts in the chunks.

## Neo4j Load Test

Apply the schema and load one article:

```powershell
.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py `
  --pmcid PMC3572442 `
  --apply-schema
```

Open Neo4j Browser at:

```text
http://localhost:7474
```

Verify paper-to-entity mentions:

```cypher
MATCH (p:Paper)-[r:MENTIONS]->(e)
WHERE p.pmcid = "PMC3572442"
RETURN p.title, type(r), labels(e), e.name
LIMIT 25;
```

Verify extracted relationships:

```cypher
MATCH (a)-[r]->(b)
WHERE r.source_pmcid = "PMC3572442"
  AND type(r) <> "MENTIONS"
RETURN labels(a), a.name, type(r), labels(b), b.name, r.evidence, r.confidence
LIMIT 25;
```

The load is idempotent, so rerunning the same command should not duplicate graph nodes or relationships.

## Makefile Usage

Run the full pipeline through `make`:

```powershell
make ingest-pmc PMCIDS="PMC3572442 PMC3234107" MODEL_PROFILE=frontier ARGS="--apply-schema"
```

Run a cheap artifact-only check:

```powershell
make ingest-pmc PMCIDS="PMC3572442" MODEL_PROFILE=noop ARGS="--skip-load"
```

Run a local model artifact-only check:

```powershell
make ollama-pull LOCAL_MODEL=qwen2.5:7b-instruct
make ingest-pmc PMCIDS="PMC3572442" MODEL_PROFILE=local-qwen25 ARGS="--skip-load"
```

## Useful Options

| Option | Purpose |
| --- | --- |
| `--pmcid` | One or more PMC IDs from the command line. |
| `--pmcid-file` | Plain text file with one PMCID per line. |
| `--limit` | Process only the first N normalized IDs. |
| `--output-root` | Override the artifact root. Default is `data/source_documents/pmc_v001`. |
| `--clean-output` | Delete the output root before writing new artifacts. |
| `--chunk-max-chars` | Maximum chunk size in characters. |
| `--chunk-overlap-chars` | Character overlap between chunks. |
| `--model-profile` | Select `frontier`, `local-qwen25`, `local-qwen3`, or `noop`. |
| `--extractor` | Override the profile extractor with `openai`, `gliner_ollama`, or `noop`. |
| `--model` | Override the profile relation/frontier model. |
| `--entity-model` | Override the GLiNER model used by `gliner_ollama`. |
| `--skip-load` | Do not write to Neo4j. |
| `--apply-schema` | Apply Cypher schema before Neo4j loading. |
| `--min-confidence` | Drop model relationships below this confidence. |
| `--fail-fast` | Stop on the first article or chunk error. |

## Regression Tests

Run the focused unit tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Run a syntax/import compile check:

```powershell
.\.venv\Scripts\python.exe -m compileall pipelines packages scripts tests
```

## Recommended Test Progression

1. Run `--model-profile noop --skip-load`.
2. Run OpenAI extraction with `--skip-load`.
3. Start Neo4j and run with `--apply-schema`.
4. Query Neo4j for `MENTIONS` and extracted relationships.
5. Rerun the same PMCID to confirm idempotent loading.
