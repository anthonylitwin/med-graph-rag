# MedGraphRAG Presentation Content

## Presentation Mode Key

Use these tags while building slides and rehearsing:

- **Demo:** show the working application briefly.
- **Diagram:** show a static visual or Mermaid-derived diagram.
- **Verbal:** explain without live interaction; keep the slide sparse.

Recommended pacing: keep the live demo to 3-5 minutes total. Demo the application as proof that the pipeline exists end to end, but keep the capstone argument centered on data representation, evaluation, and known limits.

## Demo Run-of-Show

1. **Slide 1 or 3, 20-30 seconds - Demo:** Open the Home page and point to the active runtime/profile. This establishes that there is a real local system behind the diagrams.
2. **Slide 6, 60-90 seconds - Demo:** Open Graph, search a known biomedical term such as `statins`, `LDL`, or `triglycerides`, then click a node or relationship to show labels, properties, evidence, PMCID, and chunk provenance.
3. **Slide 7, 90-120 seconds - Demo:** Open Chat and ask one prepared question that reliably returns graph evidence and sources. Highlight the answer, source snippets, and reasoning path. Have one abstention question ready only if you want to demonstrate safety behavior.
4. **Slide 8 or 10, optional 30-45 seconds - Demo:** Show Ingestion or Admin only if time permits. Use it to show queues/artifacts/counts, not to run a long extraction live.

What not to live-demo unless specifically asked: full PMC ingestion, model downloads, schema setup, DVC/MLflow runs, clearing Neo4j, or long extraction jobs. Diagram or verbally explain those because they are slow, brittle in a presentation setting, or operational rather than conceptual.

## Slide 1 - MedGraphRAG

- Research question: can structured graph evidence improve traceable biomedical QA?
- Domain: PMC literature on lipids and cardiovascular disease
- Output: cited answer, or abstention when evidence is insufficient
- System boundary: experimental literature QA prototype, not a clinical decision tool

**Delivery mode:** **Demo + Verbal.** Optionally begin with the Home page for 20-30 seconds, then return to the title slide.

**Can demo:** Home page, active runtime/profile, main navigation to Chat/Graph/Ingestion/Admin.

**Should diagram:** One horizontal transformation: `Article -> Graph Facts -> Evidence -> Answer`.

**Should verbally explain:** The app exists to demonstrate the data-science pipeline end to end; the capstone claim is about representation, grounding, and measured failure modes.

**Speaker objective:** Frame the project as a data-representation experiment implemented as an end-to-end application, not primarily as a software architecture project.

## Slide 2 - The Data Science Problem

- Biomedical findings are distributed across long, heterogeneous prose
- Synonyms obscure identity: `LDL-C` = `low-density lipoprotein cholesterol`
- Relationships, direction, uncertainty, and provenance are implicit
- Goal: structured facts that remain linked to source evidence

**Delivery mode:** **Diagram + Verbal.**

**Can demo:** Skip live demo here unless asked; the app does not make the problem clearer than a focused visual.

**Should diagram:** Split slide: dense article text on the left; a small typed, cited graph on the right.

**Should verbally explain:** Raw text is flexible but hard to query; structure gains identity, relation type, direction, and provenance while losing some nuance.

**Speaker objective:** Explain why retrieval over raw text is difficult and what new information becomes explicit after transformation.

## Slide 3 - End-to-End Data Transformation

- BioC JSON -> cleaned article text -> overlapping chunks
- Chunks -> typed mentions -> normalized entities
- Entity pairs -> scored relations -> validated graph records
- Graph paths + definitions -> evidence objects -> answer

**Delivery mode:** **Diagram + optional Demo.**

**Can demo:** Briefly return to Home and point at the workflow cards if you want a quick bridge from slide pipeline to application workflow.

**Should diagram:** Use Diagram A below, with the data form in large text and the operation in a small arrow label.

**Should verbally explain:** Each stage changes the data representation and creates both useful structure and a possible error boundary.

**Speaker objective:** Give the audience the complete map once. Emphasize that each stage changes the representation and introduces both value and possible loss.

## Slide 4 - Raw Text to Chunks

- Main default: 6,000 characters, 500-character overlap
- Word-boundary preference; stable PMCID chunk IDs
- Retains offsets, order, section/type, and source sections
- Trade-off: bounded context vs duplicated text and missed cross-chunk facts

**Delivery mode:** **Diagram + Verbal.**

**Can demo:** Avoid live demo. Chunking artifacts are better shown as a static visual or a prepared artifact screenshot if needed.

**Should diagram:** A document strip divided into three overlapping colored windows; annotate IDs and character offsets.

**Should verbally explain:** Chunking is a modeling choice. The defaults are implemented choices, not proven-optimal settings from a completed ablation.

**Speaker objective:** Explain why extraction is performed on bounded windows and why chunking is a modeling decision, not merely preprocessing.

## Slide 5 - Text to Structured Knowledge

- Text: `...optimal LDL-C reduction on statin monotherapy...`
- Entities: `Statins: Drug`; `LDL-C: Biomarker`
- Normalize: `LDL-C -> LDL cholesterol`
- Fact: `(Statins)-[:REDUCES]->(LDL cholesterol)` + evidence + chunk

**Delivery mode:** **Diagram + Verbal.**

**Can demo:** Do not run extraction live. If asked, show Ingestion only as the UI that queues jobs and exposes artifacts.

**Should diagram:** Use Diagram B below. Mark the example as "human-reviewed gold example."

**Should verbally explain:** This is the key representational move: prose becomes schema-constrained, queryable data while the evidence excerpt remains attached.

**Speaker objective:** Walk slowly through the most important transformation: prose becomes schema-constrained, queryable data while the evidence excerpt remains attached.

## Slide 6 - Building the Knowledge Graph

- Entity ID: type + normalized-name slug
- Nodes merged by ID; relationships merged by evidence-specific hash
- `Paper-[:MENTIONS]->Entity` preserves document membership
- Fact edges retain confidence, PMCID, chunk, model, and graph run

**Delivery mode:** **Demo + Diagram.**

**Can demo:** In Graph, search for `statins`, `LDL`, or `triglycerides`; filter by label or relationship type if helpful; click a relationship and point to evidence/provenance fields in the inspector or raw JSON.

**Should diagram:** Structured JSON card feeding a three-node graph with a Paper node and one fact edge.

**Should verbally explain:** Neo4j is the storage/query mechanism; the scientific object is the evidence-bearing graph representation and the identity/provenance decisions behind it.

**Speaker objective:** Focus on the representational change from records to connected facts. Explain both the deduplication benefit and the limitation of name-based identity.

## Slide 7 - Graph to Answer

- Question terms expand through curated aliases/definitions
- Full-text/substr entity anchoring -> direct or two-hop Cypher paths
- Heuristic ranking returns up to 12 evidence objects
- Extractive answer or Qwen 2.5 evidence-only JSON; otherwise abstain

**Delivery mode:** **Demo + Diagram.**

**Can demo:** In Chat, ask one prepared question that reliably returns sources and a reasoning path. Suggested prepared prompts:
    - `What does statin therapy reduce?`
    - `How are triglycerides associated with cardiovascular risk?`
    - `What evidence links LDL cholesterol and cardiovascular disease?`

**Should diagram:** Use Diagram D below and display one evidence object with endpoints, evidence excerpt, and chunk ID.

**Should verbally explain:** The answer model receives graph evidence objects and optional definitions, not semantically retrieved text chunks. The UI should be used to show grounding: answer, source snippets, confidence/abstention, and reasoning path.

**Speaker objective:** Show exactly what the answer model receives. State clearly that the current implementation is graph retrieval plus optional definitions, not vector chunk retrieval.

## Slide 8 - Two Evaluation Layers

- **Graph construction:** entity and relation precision / recall / F1
- Latest full current run: entity F1 **0.528**; relation F1 **0.086**
- **QA:** retrieval, fact coverage, citations, paths, abstention
- Latest six-question dev run: retrieval **0.333**; answer accuracy **0.333**
- DVC reproduces state; MLflow compares parameters, metrics, artifacts

**Delivery mode:** **Diagram + Verbal; optional Demo.**

**Can demo:** If there is time, show Ingestion job artifacts or Admin graph counts as operational proof. Do not run evaluation live.

**Should diagram:** Two parallel scorecards separated by a vertical line; use Diagram C for the graph-construction side.

**Should verbally explain:** Evaluation is the sober part of the talk. The relation F1 is the main bottleneck, and the QA set is diagnostic rather than a superiority claim.

**Speaker objective:** Make relationship extraction the identified bottleneck and avoid overstating small development-set results. Explain why graph accuracy and QA accuracy must be diagnosed separately.

## Slide 9 - Key Decisions and Trade-offs

- 6,000/500 chunks: context preservation vs pair ambiguity
- Strict ontology: queryability vs loss of nuance and out-of-schema facts
- Local non-instruction extraction: auditability/locality vs low relation F1
- Name normalization: fewer duplicates vs false merges/splits
- Graph paths: explicit structure vs incomplete graph coverage

**Delivery mode:** **Verbal + Diagram.**

**Can demo:** Skip live demo; this slide is where you interpret the system rather than operate it.

**Should diagram:** Five balanced scales or a two-column "gain / cost" table.

**Should verbally explain:** Connect each limitation to a specific representation choice. This makes the low metrics look like a measured diagnosis rather than a vague failure.

**Speaker objective:** Demonstrate that every transformation encodes assumptions. Connect observed errors to those decisions rather than treating the pipeline as a black box.

## Slide 10 - Conclusion and Next Experiment

- Achieved: raw PMC prose -> traceable graph evidence -> cited QA
- Main bottleneck: relation semantics, direction, and coverage
- Next: schema-gold audit, larger PMCID holdout, relation calibration
- Then: hybrid graph + vector baseline, cross-chunk links, cost/latency metrics

**Delivery mode:** **Verbal + Diagram.**

**Can demo:** Only if the audience asks to see another UI surface. Otherwise end on the argument, not the interface.

**Should diagram:** Repeat the Slide 3 pipeline; highlight relation extraction in amber and future evaluation additions in blue.

**Should verbally explain:** Completed functionality is end-to-end and inspectable; the next experiment is about making the comparison and relation extraction more defensible.

**Speaker objective:** End with the data-transformation contribution and a disciplined next-step sequence. Separate completed functionality from proposed improvements.

---

# Deliverable 3 - Diagram Specifications

## Diagram A - Full Data Transformation Pipeline

**Boxes/nodes, left to right:**

1. `PMC BioC JSON` - metadata + passage objects
2. `Parsed Article` - cleaned contiguous text + passage provenance
3. `Overlapping Chunks` - text + ID + offsets + sections
4. `Typed Mentions` - Drug / Condition / Symptom / RiskFactor / Biomarker
5. `Normalized Graph Records` - canonical entities + scored relations + evidence
6. `Neo4j Knowledge Graph` - Paper/entity nodes + typed edges
7. `Retrieved Evidence` - ranked direct/two-hop paths + definitions
8. `QA Context` - up to 12 schema-shaped evidence objects
9. `Answer` - text + citations + reasoning path + abstention

**Arrows:** `fetch/parse`, `6,000 chars + 500 overlap`, `GLiNER`, `normalize/score/validate`, `MERGE`, `full-text + Cypher rank`, `assemble`, `extract or generate`.

**Optional grouping:** Group boxes 1-3 as **Text representation**, 4-6 as **Knowledge construction**, and 7-9 as **Evidence-grounded QA**. Use a small warning marker below chunks ("cross-chunk relations may be lost") and below graph records ("extraction errors become graph errors").

```mermaid
flowchart LR
    A["PMC BioC JSON<br/>metadata + passages"] -->|parse + clean| B["Parsed Article<br/>text + passage provenance"]
    B -->|6000 chars / 500 overlap| C["Chunks<br/>ID + offsets + sections"]
    C -->|GLiNER| D["Typed Mentions<br/>5 biomedical types"]
    D -->|alias / cosine normalize<br/>score + validate| E["Graph Records<br/>entities + relations + evidence"]
    E -->|MERGE by deterministic IDs| F["Knowledge Graph<br/>nodes + typed edges"]
    F -->|full-text anchor + Cypher paths| G["Retrieved Evidence<br/>ranked edges / 2-hop paths"]
    G -->|add curated definitions<br/>limit to 12| H["QA Context<br/>schema-shaped JSON"]
    H -->|extract or Qwen 2.5| I["Answer<br/>citations + abstention"]
```

## Diagram B - Extraction Example

**Actual project sentence:** `"...continuing risk despite optimal LDL-C reduction on statin monotherapy remains high..."`

**Boxes/nodes:**

1. `Raw sentence` - the sentence above
2. `Detected mentions` - `Statins -> Drug`; `LDL-C -> Biomarker`
3. `Normalized entities` - `Statins`; `LDL cholesterol` (`LDL-C` retained as mention text)
4. `Structured relation` - `source=Statins`, `type=REDUCES`, `target=LDL cholesterol`
5. `Graph + evidence` - two nodes, a directed edge, evidence text, PMCID, chunk ID, confidence

**Arrows:** `GLiNER`, `terminology normalization`, `relation extraction + validation`, `load`.

**Optional grouping:** Put boxes 2-4 inside **Structured extraction record**. Add a caption: "Human-reviewed gold example from PMC3234107; target representation, not a claim of perfect current extraction."

```mermaid
flowchart LR
    A["Sentence:<br/>optimal LDL-C reduction<br/>on statin monotherapy"] -->|GLiNER| B["Mentions<br/>Statins: Drug<br/>LDL-C: Biomarker"]
    B -->|alias normalization| C["Canonical entities<br/>Statins<br/>LDL cholesterol"]
    C -->|typed relation + validator| D["Statins --REDUCES--> LDL cholesterol"]
    D -->|attach provenance| E["Evidence-bearing edge<br/>quote + PMCID + chunk + confidence"]
```

## Diagram C - Evaluation Pipeline

**Boxes/nodes:**

1. `Reviewed Gold Data` - 5 papers; 43 chunks; accepted entities/relations
2. `Frozen Model + Parameters` - profile, thresholds, terminology, code version
3. `Extraction Run` - one prediction set per chunk
4. `Canonical Match Keys` - entity: chunk/type/name; relation: chunk/type/typed endpoints
5. `TP / FP / FN` - overall and per type
6. `Precision / Recall / F1`
7. `DVC + MLflow` - dependencies/outputs + parameters/metrics/artifacts

**Arrows:** gold and predictions both feed canonical matching; matching feeds counts; counts feed metrics; run state and metrics feed DVC/MLflow.

**Optional grouping:** Show gold and predicted data as parallel lanes. Add "artifact-only: Neo4j is not modified" beneath the extraction run.

```mermaid
flowchart LR
    G["Reviewed Gold<br/>5 papers / 43 chunks"] --> M["Exact Canonical Match<br/>chunk + type + names + endpoints"]
    P["Frozen Parameters"] --> R["Extraction Run<br/>predictions by chunk"]
    R --> M
    M --> C["TP / FP / FN<br/>overall + per type"]
    C --> S["Precision / Recall / F1"]
    P --> T["DVC + MLflow"]
    R --> T
    S --> T
```

## Diagram D - QA Retrieval Pipeline

**Boxes/nodes:**

1. `Question` - natural language
2. `Question Terms` - normalized tokens + aliases + intent cues
3. `Graph Anchors` - Neo4j full-text index or substring match
4. `Candidate Evidence` - direct edges; optional two-hop paths; curated definitions
5. `Ranked Context` - term/concept/relation/path/confidence score; maximum 12
6. `Answerer` - extractive rule or Qwen 2.5 with evidence-only prompt
7. `Output` - answer + sources + ordered reasoning path, or abstention

**Arrows:** `normalize/expand`, `anchor`, `Cypher traverse`, `score/deduplicate`, `compose`, `return`.

**Optional grouping:** Group boxes 2-5 as **Retrieval**, box 6 as **Generation**, and box 7 as **Auditable output**. Use a dashed arrow from `Curated definitions` into candidate evidence to show that definitions are separate from PMC graph facts.

```mermaid
flowchart LR
    Q["Question"] -->|normalize + aliases| T["Terms + intent cues"]
    T -->|full-text / substring| A["Graph anchor nodes"]
    A -->|direct or cue-triggered 2-hop Cypher| E["Candidate graph evidence"]
    D["Curated definitions"] -.-> E
    E -->|heuristic rank + dedupe| C["Context<br/>up to 12 evidence objects"]
    C -->|extractive rule or evidence-only Qwen| L["Answerer"]
    L --> O["Answer + citations + path<br/>or abstention"]
```
