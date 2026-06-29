# Ingestion Pipelines

The ingestion package handles PMC source-document acquisition, chunking,
biomedical extraction, validation, artifact writing, and optional Neo4j loading.

Use the detailed guide for command examples and verification:

- `pipelines/ingestion/README_pmc_ingest.md`

Related workflows:

- `pipelines/annotation/README.md`: runs PMC fetch/chunk/extract in artifact-only
  mode, records model-call audit JSON, and exports a silver annotation workbook
  for human review.
- `docs/complete_test_run.md`: full repo runbook covering setup, ingestion,
  annotation bootstrap, QA, UI, and troubleshooting.
