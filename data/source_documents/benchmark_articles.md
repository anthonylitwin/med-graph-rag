# MedGraphRAG Biomedical Literature Seed Set

## Cardiovascular Disease, Lipids, Statins, Fenofibrate, and Fish Oil Literature

| #  | Title                                                                                         | PMC ID      | Primary Topics                                      |
| -- | --------------------------------------------------------------------------------------------- | ----------- | --------------------------------------------------- |
| 1  | Hyperlipidemia as a Risk Factor for Cardiovascular Disease                                    | PMC3572442  | Hyperlipidemia, cardiovascular disease, cholesterol |
| 2  | The Role of Triglycerides in Atherosclerosis                                                  | PMC3234107  | Triglycerides, atherosclerosis, cardiovascular risk |
| 3  | Triglyceride-rich lipoproteins as a causal factor for cardiovascular disease                  | PMC4866746  | Triglycerides, cardiovascular disease               |
| 4  | Triglyceride and cardiovascular risk: A critical appraisal                                    | PMC4911828  | Triglycerides, cardiovascular outcomes              |
| 5  | Evolving targets for lipid-modifying therapy                                                  | PMC4287928  | Lipid lowering therapies, statins                   |
| 6  | Benefits of statin therapy and compliance in high risk cardiovascular patients                | PMC2952453  | Statins, cardiovascular prevention                  |
| 7  | Triglycerides and risk of cardiovascular events in statin-treated patients                    | PMC10373341 | Statins, triglycerides, cardiovascular events       |
| 8  | Triglycerides and Cardiovascular Outcomes—Can We REDUCE Residual Risk?                        | PMC7054063  | Residual cardiovascular risk, triglycerides         |
| 9  | High Triglycerides Are Associated With Increased Cardiovascular Events                        | PMC6201477  | Triglycerides, heart disease                        |
| 10 | The Association between Triglycerides and Incident Cardiovascular Disease                     | PMC7492406  | Triglycerides, cardiovascular disease               |
| 11 | Role of fibrates in cardiovascular disease prevention                                         | PMC6067007  | Fenofibrate, fibrates, cardiovascular prevention    |
| 12 | Fibrates Revisited: Potential Role in Cardiovascular Risk Reduction                           | PMC7188966  | Fenofibrate, triglycerides                          |
| 13 | Effects of Fenofibrate Treatment on Cardiovascular Disease Risk                               | PMC2646035  | Fenofibrate, cardiovascular risk                    |
| 14 | Association of Fenofibrate Therapy With Long-term Cardiovascular Risk                         | PMC5470410  | Fenofibrate, cardiovascular outcomes                |
| 15 | Use of fenofibrate on cardiovascular outcomes in statin users                                 | PMC6763755  | Fenofibrate, statin combination therapy             |
| 16 | Effectiveness and Safety of Fenofibrate in Routine Treatment                                  | PMC10594425 | Fenofibrate, safety, lipid reduction                |
| 17 | Effect of fenofibrate in patients with elevated triglycerides                                 | PMC6171908  | Fenofibrate, hypertriglyceridemia                   |
| 18 | Fenofibrate's impact on cardiovascular risk in patients with metabolic syndrome               | PMC11264858 | Fenofibrate, metabolic syndrome                     |
| 19 | Fenofibrate plus statin and ASCVD risk by triglyceride-rich lipoproteins                      | PMC13101280 | Fenofibrate, statins, ASCVD                         |
| 20 | Association of fenofibrate therapy with cardiovascular events                                 | PMC12955317 | Fenofibrate, cardiovascular events                  |
| 21 | Fish oil – how does it reduce plasma triglycerides?                                           | PMC3563284  | Fish oil, triglycerides                             |
| 22 | Fish oil supplementation modifies the genetic potential for lipid levels                      | PMC10557817 | Fish oil, lipids                                    |
| 23 | A Double-Blind Randomized Trial of Fish Oil to Lower Cardiovascular Risk                      | PMC5646219  | Fish oil, cardiovascular risk                       |
| 24 | Role of omega-3 fatty acids in prevention and treatment of cardiovascular disease             | PMC9791266  | Omega-3, cardiovascular disease                     |
| 25 | Effect of omega-3 fatty acids on cardiovascular outcomes                                      | PMC8413259  | Omega-3, cardiovascular outcomes                    |
| 26 | The Role of n-3 Long Chain Polyunsaturated Fatty Acids in Cardiovascular Disease              | PMC6024670  | Omega-3, cardiovascular disease                     |
| 27 | Association Between Omega-3 Fatty Acid Intake and Cardiovascular Risk                         | PMC10381976 | Omega-3, cardiovascular risk                        |
| 28 | Effects of n-3 fatty acids on major cardiovascular events                                     | PMC3388014  | Omega-3, cardiovascular events                      |
| 29 | The effect of omega-3 fatty acids and combination with statins on lipid profile               | PMC9609787  | Omega-3, statins, lipid profile                     |
| 30 | Comparison of efficacy and safety of combination therapy with statins and omega-3 fatty acids | PMC6320142  | Statins, omega-3, combination therapy               |

---

# Suggested Initial Extraction Targets

## High Value Drug Nodes

* Statins
* Fenofibrate
* Fish Oil
* Omega-3 Fatty Acids
* Aspirin
* Niacin

---

## High Value Biomarker Nodes

* LDL Cholesterol
* HDL Cholesterol
* Triglycerides
* Total Cholesterol
* ApoB
* Non-HDL Cholesterol

---

## High Value Condition Nodes

* Hypertriglyceridemia
* Hypercholesterolemia
* Cardiovascular Disease
* Atherosclerosis
* Myocardial Infarction
* Acute Pancreatitis
* Metabolic Syndrome

---

# Expected High-Frequency Relationships

```text
(Drug)-[:REDUCES]->(Biomarker)
(Drug)-[:PREVENTS]->(Condition)
(Biomarker)-[:ASSOCIATED_WITH]->(Condition)
(RiskFactor)-[:INCREASES_RISK_OF]->(Condition)
(Drug)-[:INTERACTS_WITH]->(Drug)
```

---

# Recommended Use in MedGraphRAG Pipeline

## Phase 1 — Entity Extraction Benchmarking

Goal:

* Benchmark frontier models vs local models
* Validate ontology coverage
* Measure extraction precision/recall

Recommended Output:

* JSON extraction objects
* Gold labeled relationship set

---

## Phase 2 — Graph Construction

Goal:

* Convert extracted entities/relationships into Neo4j graph
* Deduplicate normalized entities
* Attach evidence spans to edges

Recommended Features:

* Deterministic IDs
* Confidence thresholds
* Provenance tracking

---

## Phase 3 — Question Answering

Goal:

* Compare:

  * Standard RAG
  * GraphRAG
  * Hybrid retrieval

Example Questions:

* Which drugs reduce triglycerides?
* What conditions are associated with elevated triglycerides?
* Which therapies prevent myocardial infarction?
* What adverse effects are associated with statins?

---

# Recommended Metadata to Store Per Paper

```json id="kn2zw4"
{
  "pmid": "",
  "pmcid": "",
  "title": "",
  "journal": "",
  "year": "",
  "doi": "",
  "authors": [],
  "mesh_terms": [],
  "keywords": [],
  "download_url": "",
  "ingestion_timestamp": ""
}
```
