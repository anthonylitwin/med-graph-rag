<script setup lang="ts">
import { onMounted, ref } from 'vue'
import heroImage from '../assets/hero.png'
import { getActiveModelRuntime, type ActiveModelRuntime } from '../lib/apiClient'

const runtime = ref<ActiveModelRuntime | null>(null)
const runtimeError = ref<string | null>(null)
const isLoadingRuntime = ref(true)

const workflowSteps = [
  {
    label: 'Ingest',
    title: 'Source Documents',
    description: 'Queue PMC IDs or pasted text, chunk the source material, and keep run artifacts for review.',
  },
  {
    label: 'Extract',
    title: 'Biomedical Entities',
    description: 'Use GLiNER-BioMed to identify drugs, conditions, symptoms, risk factors, biomarkers, and papers.',
  },
  {
    label: 'Normalize',
    title: 'Terminology Matching',
    description: 'Map surface mentions onto canonical biomedical concepts with alias and semantic matching.',
  },
  {
    label: 'Score',
    title: 'Relationship Candidates',
    description: 'Rank relation candidates with cosine similarity, lexical cues, proximity, and entity confidence.',
  },
  {
    label: 'Retrieve',
    title: 'Neo4j Graph Evidence',
    description: 'Store extracted facts in Neo4j and retrieve grounded evidence paths for biomedical questions.',
  },
  {
    label: 'Answer',
    title: 'GraphRAG Responses',
    description: 'Generate answers with source snippets, confidence, abstention, and a transparent reasoning path.',
  },
]

const modelProfiles = [
  {
    name: 'local-non-instruct',
    label: 'Local non-instruct pipeline',
    description: 'Default app profile using Ollama QA, GLiNER-BioMed entities, terminology normalization, and semantic relation scoring.',
  },
  {
    name: 'local-gliner',
    label: 'Local GLiNER',
    description: 'Runs Ollama for QA with non-generative GLiNER-BioMed entity extraction.',
  },
  {
    name: 'local-qwen25 / local-qwen3',
    label: 'Local Qwen experiments',
    description: 'Experiment profiles that pair Ollama Qwen models with GLiNER-assisted generative extraction.',
  },
  {
    name: 'frontier',
    label: 'Frontier API experiments',
    description: 'Uses the configured OpenAI frontier model for extraction and QA in experiment workflows.',
  },
  {
    name: 'noop',
    label: 'Noop smoke test',
    description: 'Deterministic fixtures for exercising plumbing without external model or database dependencies.',
  },
]

const launchLinks = [
  {
    label: 'Chat',
    title: 'Ask Questions',
    description: 'Submit biomedical questions and inspect grounded answers, sources, and reasoning paths.',
    to: '/chat',
  },
  {
    label: 'Graph',
    title: 'Explore Evidence',
    description: 'Browse nodes and relationships directly in the Neo4j-backed biomedical graph.',
    to: '/graph',
  },
  {
    label: 'Ingestion',
    title: 'Build The Graph',
    description: 'Queue PMC IDs or plain text, track extraction jobs, and inspect generated artifacts.',
    to: '/ingestion',
  },
  {
    label: 'Admin',
    title: 'Operate Neo4j',
    description: 'Check graph counts and manage local database maintenance controls.',
    to: '/administration',
  },
]

function displayValue(value?: string | null) {
  return value && value.trim() ? value : '-'
}

onMounted(async () => {
  try {
    runtime.value = await getActiveModelRuntime()
  } catch (error) {
    runtimeError.value = error instanceof Error ? error.message : 'Server unavailable'
  } finally {
    isLoadingRuntime.value = false
  }
})
</script>

<template>
  <main class="home-page">
    <section class="hero-section">
      <div class="hero-copy">
        <p class="eyebrow">
          Biomedical GraphRAG Workbench
        </p>
        <h1>MedGraphRAG</h1>
        <p class="lede">
          A local-first workspace for turning biomedical documents into a queryable knowledge graph, then using
          graph-grounded retrieval to answer questions with evidence.
        </p>

        <div class="hero-actions">
          <RouterLink
            class="button button-primary"
            to="/chat"
          >
            Open Chat
          </RouterLink>
          <RouterLink
            class="button button-secondary"
            to="/graph"
          >
            Browse Graph
          </RouterLink>
        </div>
      </div>

      <aside class="runtime-panel">
        <img
          :src="heroImage"
          alt=""
          class="runtime-art"
        >
        <div class="panel-header">
          <div>
            <p class="eyebrow">
              Current Runtime
            </p>
            <h2>{{ runtime?.label ?? (isLoadingRuntime ? 'Loading runtime' : 'Server unavailable') }}</h2>
          </div>
          <span
            class="status-pill"
            :class="{ muted: runtimeError }"
          >
            {{ runtimeError ? 'Offline' : 'Active' }}
          </span>
        </div>

        <p
          v-if="runtimeError"
          class="runtime-error"
        >
          {{ runtimeError }}
        </p>

        <dl class="runtime-list">
          <div>
            <dt>Profile</dt>
            <dd>{{ displayValue(runtime?.name) }}</dd>
          </div>
          <div>
            <dt>QA</dt>
            <dd>{{ displayValue(runtime?.qa_provider) }} / {{ displayValue(runtime?.qa_model) }}</dd>
          </div>
          <div>
            <dt>Retriever</dt>
            <dd>{{ displayValue(runtime?.qa_retriever) }}</dd>
          </div>
          <div>
            <dt>Extractor</dt>
            <dd>{{ displayValue(runtime?.extractor_provider) }} / {{ displayValue(runtime?.extractor_model) }}</dd>
          </div>
          <div>
            <dt>Entities</dt>
            <dd>{{ displayValue(runtime?.entity_model) }}</dd>
          </div>
        </dl>
      </aside>
    </section>

    <section class="launch-grid">
      <RouterLink
        v-for="link in launchLinks"
        :key="link.to"
        class="launch-card"
        :to="link.to"
      >
        <span>{{ link.label }}</span>
        <strong>{{ link.title }}</strong>
        <p>{{ link.description }}</p>
      </RouterLink>
    </section>

    <section class="content-section">
      <div class="section-heading">
        <p class="eyebrow">
          Technique
        </p>
        <h2>How The Pipeline Works</h2>
      </div>

      <div class="workflow-grid">
        <article
          v-for="step in workflowSteps"
          :key="step.label"
          class="workflow-card"
        >
          <span>{{ step.label }}</span>
          <h3>{{ step.title }}</h3>
          <p>{{ step.description }}</p>
        </article>
      </div>
    </section>

    <section class="content-section">
      <div class="section-heading">
        <p class="eyebrow">
          Models
        </p>
        <h2>Supported Runtime Profiles</h2>
      </div>

      <div class="profile-list">
        <article
          v-for="profile in modelProfiles"
          :key="profile.name"
          class="profile-row"
        >
          <div>
            <h3>{{ profile.label }}</h3>
            <code>{{ profile.name }}</code>
          </div>
          <p>{{ profile.description }}</p>
        </article>
      </div>
    </section>
  </main>
</template>

<style scoped>
.home-page {
  display: grid;
  gap: 28px;
  max-width: 1120px;
  margin: 0 auto;
  padding: 34px 24px 56px;
  text-align: left;
}

.hero-section {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(340px, 0.85fr);
  gap: 24px;
  align-items: stretch;
}

.hero-copy,
.runtime-panel,
.content-section {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.hero-copy {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 390px;
  padding: 42px;
}

.hero-copy h1 {
  font-size: 66px;
  margin: 6px 0 16px;
}

.lede {
  max-width: 700px;
  color: var(--text);
  font-size: 20px;
  line-height: 1.55;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 28px;
}

.runtime-panel {
  position: relative;
  overflow: hidden;
  padding: 24px;
}

.runtime-art {
  position: absolute;
  top: 12px;
  right: 10px;
  width: 150px;
  opacity: 0.22;
  pointer-events: none;
}

.panel-header,
.section-heading {
  position: relative;
  z-index: 1;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.panel-header h2,
.section-heading h2,
.workflow-card h3,
.profile-row h3 {
  margin: 0;
}

.runtime-error {
  position: relative;
  z-index: 1;
  margin-top: 14px;
  color: var(--danger);
  font-size: 14px;
}

.runtime-list {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 12px;
  margin: 28px 0 0;
}

.runtime-list div {
  display: grid;
  gap: 4px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
}

.runtime-list dt {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.runtime-list dd {
  margin: 0;
  color: var(--text-h);
  font-size: 14px;
  overflow-wrap: anywhere;
}

.launch-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.launch-card {
  display: grid;
  gap: 8px;
  min-height: 156px;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: inherit;
  padding: 18px;
  text-decoration: none;
  box-shadow: var(--shadow-sm);
  transition:
    border-color 160ms ease,
    transform 160ms ease,
    box-shadow 160ms ease;
}

.launch-card:hover {
  border-color: var(--accent);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.launch-card span,
.workflow-card span {
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}

.launch-card strong {
  color: var(--text-h);
  font-size: 20px;
}

.launch-card p,
.workflow-card p,
.profile-row p {
  margin: 0;
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
}

.content-section {
  padding: 26px;
}

.section-heading {
  margin-bottom: 18px;
}

.workflow-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.workflow-card {
  display: grid;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-muted);
  padding: 16px;
}

.profile-list {
  display: grid;
  gap: 10px;
}

.profile-row {
  display: grid;
  grid-template-columns: minmax(220px, 0.65fr) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
  border-top: 1px solid var(--border);
  padding-top: 14px;
}

.profile-row code {
  margin-top: 6px;
}

@media (max-width: 920px) {
  .hero-section,
  .launch-grid,
  .workflow-grid,
  .profile-row {
    grid-template-columns: 1fr;
  }

  .hero-copy {
    min-height: 0;
    padding: 30px;
  }
}

@media (max-width: 620px) {
  .home-page {
    padding: 24px 16px 42px;
  }

  .hero-copy,
  .runtime-panel,
  .content-section {
    border-radius: var(--radius);
  }

  .lede {
    font-size: 17px;
  }

  .hero-copy h1 {
    font-size: 40px;
  }
}
</style>
