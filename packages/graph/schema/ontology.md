# MedGraphRAG Ontology v1

## Purpose

This ontology defines the initial entity types, relationships, and property conventions used by MedGraphRAG. The goal is to provide a consistent structure for converting biomedical literature into a knowledge graph that supports retrieval, reasoning, and question answering.

---

# Entity Types

## Drug

Represents a pharmaceutical substance, medication, biologic, or therapeutic agent.

### Required Properties

| Property | Type   | Description       |
| -------- | ------ | ----------------- |
| id       | String | Unique identifier |
| name     | String | Drug name         |

### Optional Properties

| Property            | Description         |
| ------------------- | ------------------- |
| category            | Drug class          |
| mechanism_of_action | Mechanism of action |
| drugbank_id         | DrugBank identifier |
| aliases             | Alternative names   |
| description         | Summary description |

---

## Condition

Represents a disease, disorder, diagnosis, or clinical condition.

### Required Properties

| Property | Type   | Description       |
| -------- | ------ | ----------------- |
| id       | String | Unique identifier |
| name     | String | Condition name    |

### Optional Properties

| Property    | Description           |
| ----------- | --------------------- |
| mesh_id     | MeSH identifier       |
| icd10       | ICD-10 code           |
| aliases     | Alternative names     |
| description | Condition description |

---

## Symptom

Represents a patient-reported symptom or observable clinical finding.

### Required Properties

| Property | Type   | Description       |
| -------- | ------ | ----------------- |
| id       | String | Unique identifier |
| name     | String | Symptom name      |

### Optional Properties

| Property    | Description         |
| ----------- | ------------------- |
| description | Symptom description |
| aliases     | Alternative names   |

---

## RiskFactor

Represents an exposure, behavior, demographic factor, or condition that increases disease risk.

### Required Properties

| Property | Type   | Description       |
| -------- | ------ | ----------------- |
| id       | String | Unique identifier |
| name     | String | Risk factor name  |

### Optional Properties

| Property    | Description                             |
| ----------- | --------------------------------------- |
| category    | Lifestyle, environmental, genetic, etc. |
| description | Summary description                     |

---

## Paper

Represents a scientific publication or literature source.

### Required Properties

| Property | Type   | Description       |
| -------- | ------ | ----------------- |
| pmid     | String | PubMed identifier |
| title    | String | Publication title |

### Optional Properties

| Property | Description      |
| -------- | ---------------- |
| year     | Publication year |
| journal  | Journal name     |
| doi      | DOI              |
| authors  | Author list      |
| abstract | Abstract text    |

---

# Relationship Types

## TREATS

### Definition

A drug is used to treat a condition.

### Pattern

```text
(Drug)-[:TREATS]->(Condition)
```

### Example

```text
Fenofibrate TREATS Hypertriglyceridemia
```

---

## CAUSES

### Definition

One condition causes or contributes to another condition.

### Pattern

```text
(Condition)-[:CAUSES]->(Condition)
```

### Example

```text
Hypertriglyceridemia CAUSES Acute Pancreatitis
```

---

## HAS_SYMPTOM

### Definition

A condition is associated with a symptom.

### Pattern

```text
(Condition)-[:HAS_SYMPTOM]->(Symptom)
```

### Example

```text
Acute Pancreatitis HAS_SYMPTOM Abdominal Pain
```

---

## INCREASES_RISK_OF

### Definition

A risk factor increases the likelihood of a condition.

### Pattern

```text
(RiskFactor)-[:INCREASES_RISK_OF]->(Condition)
```

### Example

```text
Smoking INCREASES_RISK_OF Pancreatitis
```

---

## INTERACTS_WITH

### Definition

Two drugs have a known interaction.

### Pattern

```text
(Drug)-[:INTERACTS_WITH]->(Drug)
```

### Example

```text
Warfarin INTERACTS_WITH Aspirin
```

---

## CONTRAINDICATED_FOR

### Definition

A drug should not be used for a particular condition.

### Pattern

```text
(Drug)-[:CONTRAINDICATED_FOR]->(Condition)
```

### Example

```text
Drug X CONTRAINDICATED_FOR Pregnancy
```

---

## MENTIONS

### Definition

A paper references an entity.

### Pattern

```text
(Paper)-[:MENTIONS]->(Entity)
```

### Example

```text
Paper MENTIONS Fenofibrate
```

---

# Standard Relationship Properties

All relationships may contain:

| Property    | Description           |
| ----------- | --------------------- |
| confidence  | Extraction confidence |
| evidence    | Supporting text       |
| source_pmid | Source publication    |
| extractor   | Extraction model name |
| created_at  | Timestamp             |

---

# Standard Node Properties

All nodes may contain:

| Property   | Description      |
| ---------- | ---------------- |
| source     | Data source      |
| extractor  | Extraction model |
| created_at | Timestamp        |

---

# Future Expansion

Potential future entity types:

* Gene
* Protein
* Pathway
* Procedure
* Treatment
* Clinical Trial
* Organization
* Adverse Event

Potential future relationships:

* ASSOCIATED_WITH
* PREVENTS
* EXPRESSES
* PARTICIPATES_IN
* TARGETS
* CITES
* CO_OCCURS_WITH

---

# Version

Ontology Version: 1.0

Status: MVP / Initial Extraction Benchmarking
