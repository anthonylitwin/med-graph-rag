///////////////////////////////////////////////////////////////////////////
// MedGraphRAG Schema V1
//
// Node Labels:
//   Drug
//   Condition
//   Symptom
//   RiskFactor
//   Paper
//
// Relationship Types:
//   TREATS
//   CAUSES
//   HAS_SYMPTOM
//   INCREASES_RISK_OF
//   INTERACTS_WITH
//   CONTRAINDICATED_FOR
//   MENTIONS
///////////////////////////////////////////////////////////////////////////

///////////////////////////////////////////////////////////////////////////
// CONSTRAINTS
///////////////////////////////////////////////////////////////////////////

CREATE CONSTRAINT drug_id_unique IF NOT EXISTS
FOR (n:Drug)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT condition_id_unique IF NOT EXISTS
FOR (n:Condition)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT symptom_id_unique IF NOT EXISTS
FOR (n:Symptom)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT riskfactor_id_unique IF NOT EXISTS
FOR (n:RiskFactor)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT paper_pmid_unique IF NOT EXISTS
FOR (n:Paper)
REQUIRE n.pmid IS UNIQUE;

///////////////////////////////////////////////////////////////////////////
// INDEXES
///////////////////////////////////////////////////////////////////////////

CREATE INDEX drug_name_idx IF NOT EXISTS
FOR (n:Drug)
ON (n.name);

CREATE INDEX condition_name_idx IF NOT EXISTS
FOR (n:Condition)
ON (n.name);

CREATE INDEX symptom_name_idx IF NOT EXISTS
FOR (n:Symptom)
ON (n.name);

CREATE INDEX riskfactor_name_idx IF NOT EXISTS
FOR (n:RiskFactor)
ON (n.name);

CREATE INDEX paper_title_idx IF NOT EXISTS
FOR (n:Paper)
ON (n.title);
