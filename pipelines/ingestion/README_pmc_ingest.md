# PMC Ingestion Pipeline Usage

This document describes how to use the PMC ingestion pipeline to fetch, chunk, extract, and load articles for MedGraphRAG.

## Makefile Target

You can use the Makefile target to run the ingestion pipeline:

```sh
make ingest-pmc PMCIDS="PMC3572442 PMC3234107" ARGS="--apply-schema"
```

- `PMCIDS`: Space-separated list of PMCIDs to fetch (required)
- `ARGS`: Additional arguments to pass to the script (optional)

## Direct Python Usage

You can also run the script directly:

```sh
python pipelines/ingestion/ingest_pmc.py --pmcid PMC3572442 PMC3234107 --apply-schema
```

To run from a file, use a plain text file with one PMCID per line:

```sh
python pipelines/ingestion/ingest_pmc.py --pmcid-file data/source_documents/benchmark_pmcids.txt --limit 2
```

## Parameters

| Parameter         | Description                                                                                 | Example                        |
|-------------------|---------------------------------------------------------------------------------------------|--------------------------------|
| Parameter               | Description                                                                            | Example                                      |
|-------------------------|----------------------------------------------------------------------------------------|----------------------------------------------|
| `--pmcid`               | PMC article ID, repeatable or space-separated                                          | `--pmcid PMC3572442 PMC3234107`              |
| `--pmcid-file`          | Plain text file with one PMCID per line                                                | `--pmcid-file data/source_documents/benchmark_pmcids.txt` |
| `--output-root`         | Output directory for artifacts and manifest                                            | `--output-root data/pmc_test`                |
| `--clean-output`        | Delete output directory before writing artifacts                                       | `--clean-output`                             |
| `--chunk-max-chars`     | Maximum characters per chunk                                                           | `--chunk-max-chars 6000`                     |
| `--chunk-overlap-chars` | Overlap in characters between chunks                                                   | `--chunk-overlap-chars 500`                  |
| `--extractor`           | Extraction provider: `openai` or `noop`                                                | `--extractor noop`                           |
| `--model`               | Extractor model                                                                        | `--model gpt-5.5`                            |
| `--skip-load`           | Write artifacts without inserting into Neo4j                                           | `--skip-load`                                |
| `--apply-schema`        | Apply Cypher schema before loading                                                     | `--apply-schema`                             |

## Outputs

- `raw/`         : Raw BioC JSON from PMC
- `text/`        : Cleaned full text
- `processed/`   : Structured JSON with run, document, chunks, extractions, entities, and relationships
- `manifest.csv` : Summary of fetch, extraction, and load status per article

## Example: Fetch and Chunk One Article

```sh
make ingest-pmc PMCIDS="PMC3572442" ARGS="--extractor noop --skip-load"
```

## Example: Fetch Multiple Articles, Clean Output, Custom Chunking

```sh
make ingest-pmc PMCIDS="PMC3572442 PMC3234107" ARGS="--clean-output --chunk-max-chars 6000 --chunk-overlap-chars 500"
```

## Example: Direct Python Call

```sh
python pipelines/ingestion/ingest_pmc.py --pmcid-file data/source_documents/benchmark_pmcids.txt --limit 2 --apply-schema
```

Artifacts and manifest will be written to the output directory (default: `data/source_documents/pmc_v001`).
