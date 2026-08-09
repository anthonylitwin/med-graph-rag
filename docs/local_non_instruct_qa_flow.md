# Local Non-Instruct Question Answering Flow

This is the function path used when a biomedical question is answered through the
application with the app profile set to `local-non-instruct`. The same core QA
components are also used by the batch CLI.

```mermaid
flowchart TD
    UI["ChatPage.vue\nsubmit question"] --> Client["apiClient.sendChatMessage()\nPOST /chat"]
    Client --> Route["apps/api/app/routes/chat.py\nchat()"]
    Route --> Service["apps/api/app/services/qa_service.py\nanswer_question()"]

    Service --> Profile["get_app_model_profile()\nresolve_model_profile('local-non-instruct')\nqa_provider = ollama\nqa_model = qwen2.5:7b-instruct\nqa_retriever = graph"]
    Service --> GraphRun["get_app_graph_run_id()\nQA_GRAPH_RUN_ID or experiments/params.yaml"]
    Service --> Cache["get_qa_answerer(...)\nLRU cached by profile, model,\nretriever, graph_run_id, max_evidence"]

    Cache --> Model["get_app_language_model()\nOllamaChatModel or LocalHTTPModel"]
    Cache --> RetrieverFactory["get_retriever('graph', graph_run_id)\nreturn GraphRetriever"]
    Model --> Answerer["GraphRAGAnswerer(model, retriever,\nmax_evidence = QA_MAX_EVIDENCE)"]
    RetrieverFactory --> Answerer

    Service --> Record["QuestionRecord(id='ui-question', question=message)"]
    Record --> Answer["GraphRAGAnswerer.answer()"]

    Answer --> Retrieve["GraphRetriever.retrieve(question, limit)"]
    Retrieve --> Terms["_terms()\nload biomedical aliases + definitions\nnormalize question terms\nremove graph stop terms"]
    Terms --> Definitions["_definition_evidence()\noptional curated definition matches"]
    Terms --> StartNodes["Neo4j start node discovery\nfulltext biomedical_name_alias_fulltext_idx\nfallback exact/contains match"]
    StartNodes --> PathMode{"question asks for\nconnect/path/through?"}
    PathMode -->|yes| TwoHop["PATH_QUERY\none-hop + two-hop paths\nplus DRUG_CONNECTOR_QUERY for drug path questions"]
    PathMode -->|no| Direct["DIRECT_PATH_QUERY\none-hop graph relationships"]

    TwoHop --> Score["GraphRetriever._path_records()\nscore endpoint overlap,\nconcept coverage, relationship relevance,\nlipid action, confidence, path bonus"]
    Direct --> Score
    Score --> Rank["dedupe paths and relationships\nsort by match_score, confidence,\npath length, path id"]
    Definitions --> Evidence["retrieved evidence list\ngraph evidence + definitions"]
    Rank --> Evidence

    Evidence --> EvidenceBranch{"any evidence?"}
    EvidenceBranch -->|no| Abstain["AnswerRecord\n'I could not find supporting graph evidence'\nabstained = true"]
    EvidenceBranch -->|yes| NoopBranch{"model provider"}
    NoopBranch -->|noop| NoopAnswer["deterministic evidence sentences\nsources + reasoning path"]
    NoopBranch -->|ollama/local/openai| ExtractiveBranch{"extractive shortcut applies?"}

    ExtractiveBranch -->|graph relationship question| GraphShortcut["_extractive_graph_answer()\nanswer directly from matching graph edges"]
    ExtractiveBranch -->|definition question| DefinitionShortcut["_extractive_definition_answer()\nanswer from curated definition\noptionally summarize graph evidence"]
    ExtractiveBranch -->|no| Prompt["format_qa_prompt()\nquestion + retrieved evidence\nqa_answer_json_schema()"]
    Prompt --> LLM["model.generate_json()"]
    LLM --> Complete["_complete_answer_with_top_evidence()\nappend evidence summary if answer\nmisses required top evidence"]
    Prompt -->|model error| Fallback["_fallback_answer_from_evidence()\nreturn evidence summary with model error"]

    Abstain --> Response["ChatResponse\nanswer, sources, reasoningPath,\nmodel, provider, profile,\nconfidence, abstained"]
    NoopAnswer --> Response
    GraphShortcut --> Response
    DefinitionShortcut --> Response
    Complete --> Response
    Fallback --> Response
```

## Batch CLI Path

The batch runner uses the same retriever and answerer, but writes artifacts for
inspection.

```mermaid
flowchart TD
    CLI["pipelines/qa/answer_questions.py\n--question or --question-file"] --> Args["collect_questions()\nread JSON/JSONL or CLI questions"]
    CLI --> Profile["resolve_model_profile()\nprofile plus CLI overrides"]
    Args --> Config["QAConfig(...)"]
    Profile --> Config
    Config --> Process["pipelines/qa/pipeline.py\nprocess_questions()"]
    Process --> Dirs["ensure_output_directories()\nretrieved/ + answers/"]
    Process --> Retriever["get_retriever(config.retriever)"]
    Process --> Model["get_language_model(config.answerer_provider,\nconfig.model)"]
    Retriever --> Answerer["GraphRAGAnswerer(...)"]
    Model --> Answerer
    Answerer --> Loop["for each QuestionRecord"]
    Loop --> Skip{"--skip-answer?"}
    Skip -->|yes| RetrieveOnly["retriever.retrieve()\nwrite retrieved/{question_id}.json"]
    Skip -->|no| Answer["answerer.answer()\nwrite retrieved/{question_id}.json\nwrite answers/{question_id}.json"]
    RetrieveOnly --> Manifest["manifest.csv\nupdated after each question"]
    Answer --> Manifest
```

## Key Retrieval And Answer Points

- Query entrypoint: `apps/api/app/routes/chat.py`: `chat()`
- App runtime resolution: `apps/api/app/services/qa_service.py`: `get_app_model_profile()`, `get_app_graph_run_id()`, `get_qa_answerer()`
- Batch entrypoint: `pipelines/qa/answer_questions.py`: `main()`
- Shared batch core: `pipelines/qa/pipeline.py`: `process_questions()`
- Graph retrieval: `packages/qa/retrievers.py`: `GraphRetriever.retrieve()`
- Evidence scoring: `packages/qa/retrievers.py`: `GraphRetriever._path_records()`
- Answer generation and fallbacks: `packages/qa/answerers.py`: `GraphRAGAnswerer.answer()`

For `local-non-instruct`, question answering still uses an instruct-capable local
QA model by default (`qwen2.5:7b-instruct` through Ollama). The
`local-non-instruct` part refers to the ingestion/extraction side of the profile;
QA retrieves from the graph produced by that pipeline and then answers from the
retrieved evidence.
