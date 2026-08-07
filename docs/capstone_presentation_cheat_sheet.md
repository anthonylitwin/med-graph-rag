# MedGraphRAG Presentation Cheat Sheet

This document is for the presenter, not the slides. Use the slide deck for minimal text and this sheet for technical depth. Statements labeled **future** are not implemented.

## Slide 1 — MedGraphRAG

### What I should say

“MedGraphRAG asks a data-science question: can I transform biomedical prose into a structured, traceable representation that gives a question-answering system more explicit evidence? The project starts with articles from PubMed Central, extracts typed biomedical entities and relationships, stores those facts with source evidence in a knowledge graph, and retrieves graph paths for answering questions. I built the API and web application to demonstrate the complete flow, but the core of the capstone is the sequence of data transformations and how error moves through them. The system is not a clinical decision tool. It is an experimental literature QA system whose answer should be tied to retrieved evidence or should abstain.”

### Technical concepts I should understand

- **GraphRAG:** retrieval-augmented generation in which some retrieved context is graph-structured—nodes, typed edges, and paths—rather than only raw text chunks.
- **Representation:** the data form used at a stage. The same source becomes BioC JSON, contiguous text, chunks, structured records, a graph, retrieved evidence objects, and an answer.
- **Grounding:** limiting an answer to retrieved evidence and returning citations/provenance so claims can be inspected.
- **Not a clinical validator:** traceability reduces one risk but does not establish medical correctness.

### Likely professor questions and strong answers

1. **Why use a knowledge graph?**

   A graph makes entities and typed relationships directly queryable. It supports explicit path retrieval, entity-centered aggregation across papers, and edge-level provenance. The benefit is inspectability and relational structure; it does not automatically make extracted facts correct.

2. **What is the research contribution if you also built an application?**

   The application demonstrates that the transformations can operate end to end. The data-science contribution is the implemented and evaluated mapping from unstructured literature to normalized facts, graph evidence, and grounded QA, including stage-specific failure analysis.

3. **Is this ready for clinical use?**

   No. The corpus and gold sets are small, current relation F1 is low, and the QA set is a draft development set. It is a capstone prototype for literature retrieval and experimental evaluation.

4. **What is your main result?**

   The pipeline and its evaluation are functional, but relation extraction is the main bottleneck: the latest current entity F1 is 0.528 and relation F1 is 0.086. The most defensible result is the measured diagnosis of where the representation fails, not a claim of superior QA.

## Slide 2 — The Data Science Problem

### What I should say

“A biomedical article is not a table of facts. The same concept may appear as LDL, LDL-C, or low-density lipoprotein cholesterol. A relation may be asserted, negated, qualified, limited to a population, or separated from its endpoints by several sentences. A language model can read prose, but sending large collections directly to it makes evidence selection opaque and expensive. MedGraphRAG makes a selected subset of information explicit: entity type, normalized identity, relation type and direction, confidence, evidence excerpt, and document/chunk provenance. That transformation gains queryability and traceability, but it also compresses nuance. Study design, dose, temporality, population qualifiers, tables, and out-of-schema concepts may be lost.”

### Technical concepts I should understand

- **Unstructured vs structured data:** prose permits flexible expression; structured records require predefined fields and types.
- **Ontology:** the allowed entity and relation vocabulary plus directional rules.
- **Information gain:** identity, relation type, graph connectivity, and provenance become explicit.
- **Information loss:** wording, layout, context, modality, and concepts outside the ontology may not survive.
- **Entity normalization:** mapping multiple surface forms to one canonical concept.

### Likely professor questions and strong answers

1. **What exactly is gained by structuring the text?**

   The system can ask for typed neighbors and paths, merge known aliases, rank evidence by relation and confidence, and cite the exact supporting chunk. Those operations are difficult to express reliably over an undifferentiated article collection.

2. **What data is lost during transformation?**

   BioC layout and supplied annotations are not carried forward; chunking can break long-distance context; the five-type ontology excludes many concepts; relation records compress modality, dose, time, population, and study design; normalization can hide the original term, although mention text is retained as a property.

3. **Why not send full articles to the LLM?**

   Full articles consume more context, make evidence selection less transparent, and do not scale across a corpus. Bounded extraction and retrieval create inspectable intermediate artifacts and allow stage-specific evaluation.

4. **What are the largest error sources?**

   Missed or mistyped entities, incomplete normalization, ambiguous entity pairs in one window, incorrect relation semantics/direction, crude negation handling, missed cross-chunk relations, incomplete graph coverage, and retrieval heuristics that fail to anchor the intended concept.

## Slide 3 — End-to-End Data Transformation

### What I should say

“The source is NCBI PMC Open Access BioC JSON. The parser takes the first BioC document, retains core metadata and passage provenance, collapses whitespace, and joins nonempty passages. The main pipeline then creates overlapping character chunks. Each chunk produces entity candidates, normalized entity records, and relation candidates. A common validator enforces the ontology, confidence floor, direction, and evidence requirement. Those records are merged into Neo4j. At question time, terminology expands the query, Cypher retrieves direct or two-hop graph paths, curated definitions may be added, and the result is a small JSON evidence context. Finally, direct cases may use extractive logic; otherwise a local Qwen model composes the answer using only that evidence. Every arrow changes the representation, so every arrow is also a possible error boundary.”

### Technical concepts I should understand

- **BioC JSON:** a biomedical document exchange format containing document metadata, passages, offsets, annotations, and relations.
- **Intermediate representation:** a form created for the next algorithm, such as a chunk record or evidence object.
- **Validation:** deterministic checks after model/scoring output; it enforces form and ontology but cannot prove factual truth.
- **Error propagation:** false entities create false candidate pairs; false edges pollute retrieval; missing edges cause abstention or unsupported answers.
- **Provenance:** PMCID, chunk ID, evidence text, model, timestamp, and graph run attached to records.

### Likely professor questions and strong answers

1. **Which stages are model-based and which are deterministic?**

   In the default graph builder, GLiNER performs entity detection and MiniLM supplies embeddings for normalization and relation semantics. Candidate construction, weighted scoring, validation, IDs, loading, and retrieval ranking are deterministic given those outputs. Qwen is used separately for some final answers.

2. **Why use an LLM for extraction?**

   The repository supports frontier and GLiNER-plus-Qwen extraction because generative models can map varied prose into a schema with fewer task-specific rules. However, the deployed default does not use a generative relation extractor; it uses local NER plus semantic and lexical scoring. That design lets the experiment compare quality, locality, and auditability.

3. **Where is provenance first created?**

   Document and chunk IDs/offsets are created during parsing and chunking. Relation provenance is completed during validation with evidence, PMCID/PMID, chunk, extractor, model, prompt version, and timestamp; graph-run provenance is added during loading.

4. **Can you rerun the pipeline without duplicating data?**

   Yes for identical normalized outputs. Entity and Paper nodes are merged by deterministic IDs, and relationships are merged by deterministic evidence-specific IDs. Different evidence text intentionally creates a separate relationship edge.

## Slide 4 — Raw Text to Chunks

### What I should say

“The main path uses character windows, not tokens or semantic paragraphs: a maximum of 6,000 characters and 500 characters of overlap. When a chunk is not the final one, the boundary can move backward to a space if that space occurs after 60% of the maximum window. Each chunk stores order, global start/end offsets, PMCID-based ID, its first overlapping section/type, all overlapping source sections, and its text. This keeps the operation deterministic and model-agnostic. Overlap helps a boundary fact appear in at least one intact chunk, but it duplicates mentions. It does not solve long-distance or cross-chunk relations. The chosen size is an implemented default, not a parameter established by a completed ablation study, so I should describe it as a current engineering/modeling choice and propose empirical tuning on a PMCID-held-out set.”

### Technical concepts I should understand

- **Chunk size:** maximum characters included in one extraction unit.
- **Overlap:** repeated boundary context shared by consecutive chunks.
- **Global offsets:** positions in the parsed full text, used for provenance.
- **Boundary effect:** a fact may be split so neither chunk contains both endpoints.
- **Ablation:** rerunning evaluation while changing one parameter, such as chunk size, to measure causal effect on performance.

### Likely professor questions and strong answers

1. **Why chunk documents?**

   To bound model input and candidate complexity, localize evidence, and create a unit that can be independently extracted and evaluated. Whole articles would contain many more entities and possible pairs.

2. **How did you choose 6,000 characters and 500 overlap?**

   They are repository defaults and preserve substantial local context with about 8% overlap. I do not have evidence that they are optimal. The defensible next experiment is a controlled chunk-size/overlap ablation scored on PMCID-held-out entity and relation F1 plus runtime.

3. **Why characters instead of tokens or sentences?**

   Characters make segmentation deterministic and independent of a model tokenizer. The cost is weaker linguistic boundaries. Sentence- or section-aware chunking is a plausible improvement.

4. **What happens when a relationship spans multiple chunks?**

   It is only found if overlap puts both mentions and supporting context into one extraction window. The current pipeline does not reconcile candidates across chunks, so otherwise it is missed.

5. **Does overlap create duplicates?**

   Yes. Entity records are deduplicated by deterministic ID in the processed article; relation IDs include evidence and chunk, so genuinely duplicated boundary evidence can remain as separate evidence-specific edges.

## Slide 5 — Text to Structured Knowledge

### What I should say

“In the default profile, GLiNER receives one chunk and exactly five labels: Drug, Condition, Symptom, RiskFactor, and Biomarker. Candidates below the 0.50 entity threshold are not emitted. A terminology normalizer checks an exact type-specific alias; if none matches, it compares a MiniLM embedding to known aliases and accepts a concept at cosine similarity 0.84 or higher; otherwise it keeps the cleaned surface name. For relations, typed entity pairs must appear within one sentence or a pair of adjacent sentences and within 300 characters. The score combines prototype semantic similarity, a lexical cue, proximity, and entity confidence. A simple negation check and the validator can reject a candidate. The slide example is a human-reviewed gold target: statins and LDL-C become a typed REDUCES edge to normalized LDL cholesterol with the source excerpt and chunk attached.”

### Technical concepts I should understand

- **GLiNER:** a span-based model that predicts entities for supplied natural-language labels.
- **Cosine similarity:** the normalized dot product between embedding vectors; higher values indicate closer direction in embedding space.
- **Candidate generation vs classification:** endpoint type rules generate plausible pairs; the score selects a relation and confidence.
- **Schema-constrained output:** records must use allowed fields/types and later pass deterministic validation.
- **Confidence is not probability calibration:** the weighted score ranks candidates but has not been proven to equal empirical correctness probability.

### Likely professor questions and strong answers

1. **Why use GLiNER instead of a biomedical dictionary?**

   A contextual NER model can detect unseen surface forms and use context, while a dictionary is precise but limited to listed terms. The pipeline combines contextual detection with dictionary/semantic normalization.

2. **How are entities normalized?**

   First by exact type-specific match across canonical names and aliases; second by same-type MiniLM cosine search at 0.84; otherwise by a cleaned surface form. The record retains mention text, method, score, and any curated identifiers.

3. **How do you prevent duplicate nodes?**

   Normalized entities receive deterministic IDs from type and slugged canonical name, and Neo4j merges by ID. This prevents exact normalized duplicates but does not solve all synonymy or homonymy.

4. **Why use an LLM or semantic model for relation extraction?**

   Relations vary lexically, so semantic similarity can recognize paraphrases beyond a fixed phrase list. In the current default, MiniLM is used for semantic scoring rather than a generative LLM. The frontier profile is a stronger, costlier comparison.

5. **How is hallucination controlled during extraction?**

   Candidate relations are restricted to detected endpoints, allowed directions, local evidence windows, confidence thresholds, and required evidence text. Frontier/Qwen modes use strict JSON schemas and evidence-only prompts. These controls reduce unsupported structure but do not eliminate semantic false positives.

## Slide 6 — Building the Knowledge Graph

### What I should say

“The validated extraction record is converted to a property graph. `paper:PMC3234107` is a Paper node. Biomedical entity IDs look like `drug:statins` or `biomarker:ldl_cholesterol`. For every entity found in an article, the loader creates a `MENTIONS` edge from the Paper. For every extracted fact, it creates a typed edge between entity nodes. The fact edge retains evidence, confidence, source article, chunk, extractor, model, prompt version, creation time, and graph-run provenance. Neo4j uniqueness constraints and `MERGE` make reloads idempotent. There is an important identity trade-off: a normalized-name slug is simple and deterministic, but without a broad authority identifier it can split synonyms or merge homonyms. Another design choice is evidence-specific relationship identity, so the same conceptual claim supported in two chunks can exist as two edges.”

### Technical concepts I should understand

- **Property graph:** labeled nodes and typed directed edges, both with arbitrary properties.
- **MERGE:** Neo4j operation that matches or creates a pattern, supporting idempotent loads.
- **Entity resolution:** deciding whether two mentions refer to the same real-world concept.
- **Claim vs evidence modeling:** one claim can have multiple evidence records; the current design represents these as evidence-specific edges.
- **Graph run ID:** identifies the graph-building run to prevent QA from mixing evidence across experiments.

### Likely professor questions and strong answers

1. **Why Neo4j?**

   The required operations are typed neighbor and path retrieval with property-level provenance. A property graph and Cypher express those directly. The scientific value is the graph representation, not the vendor itself.

2. **How do you know the graph is correct?**

   I do not infer correctness from successful loading. I compare predicted entities and relations against reviewed chunk-level gold labels using precision, recall, and F1, inspect per-type false positives/negatives, and separately test whether QA retrieves expected evidence.

3. **How do you prevent duplicate nodes?**

   Deterministic normalized IDs plus uniqueness constraints and `MERGE`. This handles identical canonical names, while broader ontology linking is needed for complete entity resolution.

4. **Why attach evidence to edges?**

   An edge without evidence is difficult to verify. Evidence text and chunk/article provenance allow retrieval, human inspection, and citation scoring.

5. **What is the schema–gold alignment concern?**

   Some accepted gold rows use endpoint combinations that the current validator would reject, such as `REDUCES` from a Drug to a Condition although the validator permits Drug to Biomarker. Before a formal benchmark claim, I would audit and version the ontology and gold labels together.

## Slide 7 — Graph to Answer

### What I should say

“The question is not converted into an arbitrary LLM-generated Cypher query. The retriever normalizes question tokens, expands exact concept aliases and local definition matches, and removes generic stop terms. It tries a Neo4j full-text index for starting entities, then a substring fallback. It retrieves incident non-`MENTIONS` edges and optionally two-hop paths when the question contains cues such as ‘path,’ ‘connect,’ or ‘multi-hop.’ Relation words such as ‘reduce’ can filter the requested edge types. Paths are ranked with endpoint overlap, coverage of mentioned concept groups, evidence/edge term overlap, relationship relevance, selected domain heuristics, confidence, and path bonuses. The answerer receives at most 12 evidence objects. It either builds an extractive response for some direct cases or asks Qwen for a strict evidence-only JSON answer with sources and an ordered reasoning path.”

### Technical concepts I should understand

- **Full-text index:** lexical search over entity names/aliases; this is not dense vector search.
- **Cypher traversal:** querying graph patterns such as one- or two-edge paths.
- **Hybrid evidence types:** graph-derived facts plus separate curated definitions.
- **Extractive shortcut:** deterministic answer composition from edge records before calling the model.
- **Abstention:** explicitly declining when no evidence is retrieved or the model judges evidence insufficient.

### Likely professor questions and strong answers

1. **Why not just use vector RAG?**

   Vector RAG is strong for semantically retrieving passages and would better preserve prose. The graph is useful when questions depend on typed relations, identity, or paths and when explicit evidence provenance matters. The best future comparison is a frozen plain-LLM, chunk-vector-RAG, graph-RAG, and hybrid experiment. The repository does not yet implement the plain or chunk-RAG baselines, so I do not claim graph superiority.

2. **Does the system use semantic/vector retrieval?**

   Not for QA chunks. MiniLM embeddings are used during entity normalization and relation scoring. QA anchors entities with a Neo4j full-text index or substring matching, then uses Cypher paths and heuristic ranking.

3. **How is hallucination controlled at answer time?**

   The prompt says to use only retrieved evidence, the output schema requires sources and abstention, the system abstains immediately when no evidence exists, and some direct answers are deterministic. However, false graph edges can still ground a false answer; the latest unsupported-answer rate of 0.50 shows this remains unresolved.

4. **How does multi-hop reasoning work?**

   The retriever can return two connected non-`MENTIONS` edges as an ordered path and preserve `pathId`, `pathStep`, and `pathLength`. It is limited to two hops and activated by explicit path cues, so it is structured retrieval rather than unconstrained reasoning.

5. **How would this scale to millions of articles?**

   Acquisition and extraction should be batched and incremental, models kept resident, artifacts partitioned, and graph writes bulked. Entity resolution would need external IDs, Neo4j indexes/sharding strategy would require testing, and retrieval would need precomputed embeddings or learned candidate generation. The current per-article/per-edge query loader is suitable for a prototype, not million-article throughput.

## Slide 8 — Evaluation

### What I should say

“There are two evaluation layers because they answer different questions. Extraction evaluation asks whether chunks were converted into correct entities and relations. The reviewed gold set has five papers and 43 chunks. Entity matching requires exact chunk, type, and normalized name; relation matching additionally requires exact relation and typed endpoints. The latest current non-instruction result has entity precision 0.551, recall 0.507, F1 0.528, but relation precision 0.082, recall 0.091, F1 0.086. QA evaluation asks whether expected evidence was retrieved and whether the answer covered expected facts with supported citations and correct abstention. On the latest six-question draft development set, retrieval recall and answer accuracy are both 0.333. These small-set metrics are diagnostic. DVC pins code, parameters, data dependencies, outputs, and metric files; MLflow makes configurations, per-type metrics, and artifacts comparable.”

### Technical concepts I should understand

- **Precision:** `TP / (TP + FP)`; how trustworthy positive predictions are.
- **Recall:** `TP / (TP + FN)`; how much of the gold set is recovered.
- **F1:** harmonic mean `2PR / (P + R)`; low if either precision or recall is low.
- **Exact matching:** no partial credit for synonyms unless normalized names already agree.
- **Development vs holdout:** parameters can be tuned on development data; a protected holdout is untouched until the method is frozen.
- **Artifact-only extraction evaluation:** does not alter Neo4j, preventing evaluated predictions from contaminating QA state.

### Likely professor questions and strong answers

1. **What does F1 tell you?**

   It balances false positives and false negatives through the harmonic mean of precision and recall. It is useful for an imbalanced extraction task, but it does not show which entity/relation types fail or how severe an error is, so I also inspect per-type and match artifacts.

2. **How are relationships evaluated?**

   A predicted relationship is a true positive only when chunk ID, relation type, source type/name, and target type/name all exactly match a gold key. Direction therefore matters.

3. **Why evaluate extraction separately from QA?**

   QA adds retrieval and answer-generation error. If extraction is wrong, a good answerer cannot recover missing facts; if extraction is correct but retrieval is wrong, changing the extractor will not fix QA. Separate metrics locate the bottleneck.

4. **Why use MLflow?**

   MLflow records the model/profile, thresholds, dataset, aggregate and per-type metrics, and diagnostic artifacts in one comparable run history. That prevents selecting a model from an undocumented console output.

5. **Why use DVC as well?**

   DVC describes the reproducible computation: exact parameter groups, source/data dependencies, outputs, content hashes, and metric files. MLflow is the experiment catalog; DVC pins the computational state. A remote still needs to be configured for durable cross-machine storage.

## Slide 9 — Key Decisions and Trade-offs

### What I should say

“The observed results make the trade-offs concrete. Larger chunks preserve context but create many plausible entity pairs; smaller chunks reduce ambiguity but miss long-range facts. A strict ontology makes validation and Cypher retrieval possible, but facts outside five entity types and 11 relations disappear or are forced into coarse categories. The local non-instruction extractor is inspectable: I can see semantic, cue, proximity, and NER contributions, and it avoids a generative relation call. Its current relation F1, however, is only 0.086. Normalization reduces duplicate aliases, but the nine-concept terminology is too small for full entity resolution. The graph provides explicit paths but cannot retrieve facts that were never extracted. These are not independent choices—their errors interact.”

### Technical concepts I should understand

- **Bias–variance-style trade-off in schema:** a narrow schema gives consistent labels but under-represents the domain; a broad schema increases ambiguity and annotation burden.
- **Threshold trade-off:** increasing a threshold usually raises precision and lowers recall; decreasing it does the reverse, though not monotonically for all types.
- **Model calibration:** aligning scores with observed correctness, ideally per relation type.
- **Local vs frontier:** locality, privacy, cost, latency, and reproducibility versus general instruction-following and extraction quality.
- **Fine-tuning:** adapting model weights using labeled examples; useful only when label quality and quantity justify it.

### Likely professor questions and strong answers

1. **Why compare different models?**

   They occupy different quality, cost, latency, privacy, and reproducibility points. A frontier model gives a quality reference; local instruction models test generative extraction without API dependence; GLiNER isolates NER; the non-instruction pipeline tests auditable local relations; noop validates plumbing.

2. **What is the trade-off among frontier, smaller API, local, and fine-tuned models?**

   Frontier models generally offer stronger zero-shot schema interpretation but cost more and depend on an external service. Smaller API models may reduce cost with some quality loss. Local models improve data control and marginal cost but require hardware and may be less reliable. Fine-tuning can improve a narrow task and stabilize format, but needs sufficient unbiased labels and adds training/maintenance complexity.

3. **Why is relation extraction much worse than entity extraction?**

   Relation prediction requires correct endpoints, type direction, evidence scope, negation/modality interpretation, and selection among several predicates. The current weighted sentence-level scorer can confuse coincident mentions with a stated relation and lacks syntactic and entailment modeling.

4. **Could lowering the threshold fix low recall?**

   It may increase recall, but it can also sharply increase false positives. The current run already has low relation precision, so threshold-only tuning is unlikely to solve semantic confusion; per-type error analysis and a stronger classifier are needed.

5. **Would you fine-tune now?**

   Not yet as the first action. I would first audit schema–gold consistency, create a PMCID-level holdout, measure annotator agreement, and analyze relation errors. Then I could fine-tune a relation classifier on a clean, sufficiently large development set.

## Slide 10 — Conclusion and Future Work

### What I should say

“The project successfully implements the complete transformation from PMC BioC data to cleaned text, overlapping chunks, normalized biomedical records, a provenance-bearing graph, ranked evidence, and cited or abstaining answers. The value of the graph is not that it magically guarantees correctness; it creates a testable intermediate representation. The evaluation shows that entity extraction is usable as a starting point, while relation extraction and downstream retrieval remain the main limitations. My next sequence would be: first audit ontology and gold consistency; second freeze PMCID-level development and holdout sets; third improve and calibrate relation extraction; fourth implement plain-LLM, chunk-vector-RAG, graph-RAG, and hybrid baselines using the same QA questions; fifth add cross-chunk relations, broader external-ID normalization, and formal latency/cost metrics. That sequence turns the prototype into a more defensible comparative data-science study.”

### Technical concepts I should understand

- **PMCID-level split:** all chunks from one paper must remain in one split to avoid near-duplicate leakage.
- **Hybrid graph + vector retrieval:** use dense passage retrieval for prose coverage and graph retrieval for typed paths, then rerank a combined evidence set.
- **Cross-chunk relation modeling:** link mentions across overlapping or adjacent chunks, or perform a document-level second pass.
- **Graph embeddings/GNNs:** possible future ranking or link-prediction approaches; not implemented and not automatically preferable with small gold data.
- **Scale validation:** throughput, memory, graph write rate, index size, retrieval latency, and cost should be measured rather than assumed.

### Likely professor questions and strong answers

1. **What would you do first with one more semester?**

   Audit the ontology and gold labels, establish a leakage-safe PMCID holdout, and improve relation extraction using per-type error analysis. That addresses the measured bottleneck before adding architectural complexity.

2. **What future work is most likely to improve QA?**

   Better relation precision/recall and hybrid retrieval. The latest QA failures include missing or wrong graph evidence; a stronger answer model cannot compensate reliably for that upstream deficit.

3. **Would graph embeddings or a GNN help?**

   They could help candidate ranking or link prediction after the graph and labels are sufficiently large and clean. With only a small reviewed set, they risk learning extraction artifacts and are lower priority than relation quality and evaluation design.

4. **How would you compare graph RAG with vector RAG fairly?**

   Freeze the same document corpus, PMCID splits, questions, answer model, evidence budget, and evaluation metrics. Compare plain LLM, chunk vector RAG, graph RAG, and hybrid retrieval on retrieval recall, evidence support, answer accuracy, abstention, latency, and cost.

5. **What is the strongest defensible conclusion?**

   MedGraphRAG demonstrates an auditable end-to-end data transformation and stage-separated evaluation. It shows the promise of structured provenance and graph paths, while current results identify relation construction—not application plumbing—as the limiting scientific problem.

---

## Rapid-Fire Technical Answers

- **Why chunk?** Bound input and candidate pairs; preserve localized evidence. Cost: boundary loss and duplication.
- **Current chunk parameters?** Main ingestion defaults to 6,000 characters with 500 overlap.
- **Current ontology?** Drug, Condition, Symptom, RiskFactor, Biomarker, Paper; 11 extracted relations plus generated `MENTIONS`.
- **How normalize?** Exact typed alias → MiniLM cosine ≥0.84 → cleaned surface fallback.
- **How prevent duplicate nodes?** Deterministic type/name ID + Neo4j uniqueness constraint + `MERGE`.
- **How score relations?** Semantic 0.50 + lexical cue 0.25 + proximity 0.10 + NER confidence 0.15; thresholds and endpoint rules then apply.
- **How evaluate relations?** Exact chunk, relation, source type/name, target type/name match.
- **Why F1?** It penalizes a method that achieves precision by predicting too little or recall by predicting too much.
- **How control hallucination?** Evidence-bounded candidates/prompt, strict schemas, provenance, citations, and abstention; not a guarantee against false extracted edges.
- **Does QA use vector retrieval?** No. It uses Neo4j full-text/substr anchoring and Cypher path retrieval; embeddings are used earlier in construction.
- **Why MLflow?** Compare documented parameters, metrics, and artifacts across runs.
- **Why DVC?** Reproduce the exact parameter/data/code/output state and metric files.
- **What is implemented vs future?** Implemented: graph construction, graph retrieval, definitions, local/frontier profiles, extraction/QA evaluation, DVC/MLflow. Future: true chunk-vector baseline, hybrid retrieval, cross-chunk linking, GNNs, formal cost aggregation, protected holdout.
