///////////////////////////////////////////////////////////////////////////
// MedGraphRAG Schema V1.1
//
// Node Labels:
//   Drug
//   Condition
//   Symptom
//   RiskFactor
//   Biomarker
//   Paper
//
// Relationship Types:
//   TREATS
//   PREVENTS
//   REDUCES
//   INCREASES
//   ASSOCIATED_WITH
//   HAS_ADVERSE_EFFECT
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

CREATE CONSTRAINT biomarker_id_unique IF NOT EXISTS
FOR (n:Biomarker)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT paper_id_unique IF NOT EXISTS
FOR (n:Paper)
REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT paper_pmcid_unique IF NOT EXISTS
FOR (n:Paper)
REQUIRE n.pmcid IS UNIQUE;

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

CREATE INDEX biomarker_name_idx IF NOT EXISTS
FOR (n:Biomarker)
ON (n.name);

CREATE INDEX paper_title_idx IF NOT EXISTS
FOR (n:Paper)
ON (n.title);

CREATE INDEX paper_year_idx IF NOT EXISTS
FOR (n:Paper)
ON (n.year);

///////////////////////////////////////////////////////////////////////////
// OPTIONAL PROPERTY INDEXES
///////////////////////////////////////////////////////////////////////////

CREATE INDEX drug_category_idx IF NOT EXISTS
FOR (n:Drug)
ON (n.category);

CREATE INDEX condition_mesh_id_idx IF NOT EXISTS
FOR (n:Condition)
ON (n.mesh_id);

CREATE INDEX condition_icd10_idx IF NOT EXISTS
FOR (n:Condition)
ON (n.icd10);

CREATE INDEX riskfactor_category_idx IF NOT EXISTS
FOR (n:RiskFactor)
ON (n.category);

CREATE INDEX biomarker_category_idx IF NOT EXISTS
FOR (n:Biomarker)
ON (n.category);

CREATE INDEX biomarker_unit_idx IF NOT EXISTS
FOR (n:Biomarker)
ON (n.unit);

CREATE INDEX paper_doi_idx IF NOT EXISTS
FOR (n:Paper)
ON (n.doi);

CREATE INDEX paper_journal_idx IF NOT EXISTS
FOR (n:Paper)
ON (n.journal);
