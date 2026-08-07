<script setup lang="ts">
import { computed, ref } from 'vue'
import { sendChatMessage, type ChatResponse } from '../lib/apiClient'

const message = ref('')
const response = ref<ChatResponse | null>(null)
const isLoading = ref(false)

type ReasoningStep = Record<string, unknown>

type ReasoningPathGroup = {
  id: string
  label: string
  pathLength: number
  steps: ReasoningStep[]
}

type SourceGroup = {
  id: string
  label: string
  sources: Array<Record<string, unknown>>
}

function textValue(value: unknown, fallback = ''): string {
  const text = String(value ?? '').trim()
  return text || fallback
}

function numberValue(value: unknown, fallback = 1): number {
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? number : fallback
}

function pathStepLabel(step: ReasoningStep): string {
  const pathStep = numberValue(step.pathStep)
  const pathLength = numberValue(step.pathLength)
  return pathLength > 1 ? `Hop ${pathStep}` : 'Evidence'
}

function evidenceMeta(step: ReasoningStep): string {
  const parts = [
    step.evidenceId ? `Evidence ${String(step.evidenceId)}` : '',
    step.sourcePmcid ? `PMCID ${String(step.sourcePmcid)}` : '',
    step.chunkId ? `Chunk ${String(step.chunkId)}` : '',
  ].filter(Boolean)
  return parts.join(' / ')
}

function sourceMeta(source: Record<string, unknown>): string {
  const parts = [
    source.evidenceKind ? String(source.evidenceKind) : '',
    source.sourcePmcid ? `PMCID ${String(source.sourcePmcid)}` : '',
    source.chunkId ? `Chunk ${String(source.chunkId)}` : '',
    source.confidence ? `Confidence ${Math.round(Number(source.confidence) * 100)}%` : '',
  ].filter(Boolean)
  return parts.join(' / ')
}

const reasoningPathGroups = computed<ReasoningPathGroup[]>(() => {
  const steps = response.value?.reasoningPath ?? []
  const groups = new Map<string, ReasoningPathGroup>()

  steps.forEach((step, index) => {
    const pathLength = numberValue(step.pathLength)
    const pathId = textValue(step.pathId, `path-${index + 1}`)
    const group = groups.get(pathId) ?? {
      id: pathId,
      label: pathLength > 1 ? `Path ${groups.size + 1}` : 'Direct Evidence',
      pathLength,
      steps: [],
    }
    group.pathLength = Math.max(group.pathLength, pathLength)
    group.steps.push(step)
    groups.set(pathId, group)
  })

  return Array.from(groups.values()).map((group) => ({
    ...group,
    steps: [...group.steps].sort((first, second) => numberValue(first.pathStep) - numberValue(second.pathStep)),
  }))
})

const sourceGroups = computed<SourceGroup[]>(() => {
  const groups = new Map<string, SourceGroup>()

  for (const source of response.value?.sources ?? []) {
    const kind = textValue(source.evidenceKind, 'graph').toLowerCase()
    const id = kind === 'definition' ? 'definition' : kind === 'graph' ? 'graph' : 'other'
    const label = id === 'definition'
      ? 'Curated Definition Supplements'
      : id === 'graph'
        ? 'PMC Graph Evidence'
        : 'Other Evidence'
    const group = groups.get(id) ?? { id, label, sources: [] }
    group.sources.push(source)
    groups.set(id, group)
  }

  const order = ['graph', 'definition', 'other']
  return Array.from(groups.values()).sort((first, second) => order.indexOf(first.id) - order.indexOf(second.id))
})

async function handleSubmit() {
  if (!message.value.trim()) {
    return
  }

  isLoading.value = true
  response.value = null

  try {
    response.value = await sendChatMessage({
      message: message.value,
    })
  } catch (error) {
    response.value = {
      answer: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
      sources: [],
      reasoningPath: [],
      model: 'error',
      provider: 'error',
      modelProfile: 'server-configured',
    }
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="chat-page">
    <header class="page-header">
      <p class="eyebrow">
        Graph-Grounded QA
      </p>
      <h1>Chat</h1>
      <p>Ask a biomedical question against the configured graph evidence.</p>
    </header>

    <form
      class="question-panel"
      @submit.prevent="handleSubmit"
    >
      <label for="chat-message">Question</label>
      <textarea
        id="chat-message"
        v-model="message"
        rows="5"
        placeholder="How does aspirin affect bleeding risk?"
      />

      <button
        class="primary-button"
        type="submit"
        :disabled="isLoading"
      >
        {{ isLoading ? 'Asking...' : 'Ask' }}
      </button>
    </form>

    <section
      v-if="response"
      class="response-section"
    >
      <h2>Answer</h2>
      <p>{{ response.answer }}</p>

      <h3>Model</h3>
      <p>{{ response.model }} ({{ response.provider }}, {{ response.modelProfile }})</p>

      <template v-if="typeof response.confidence === 'number'">
        <h3>Confidence</h3>
        <p>{{ Math.round(response.confidence * 100) }}%</p>
      </template>

      <p v-if="response.abstained">
        The answerer abstained because the retrieved graph evidence was insufficient.
      </p>

      <h3>Sources</h3>
      <p v-if="response.sources.length === 0">
        No sources returned.
      </p>
      <div
        v-else
        class="source-groups"
      >
        <section
          v-for="group in sourceGroups"
          :key="group.id"
          class="source-group"
        >
          <header class="source-group-header">
            <strong>{{ group.label }}</strong>
            <span>{{ group.sources.length }}</span>
          </header>
          <ol class="source-list">
            <li
              v-for="(source, index) in group.sources"
              :key="`${group.id}-${index}`"
              class="source-item"
            >
              <div class="source-heading">
                <strong>{{ textValue(source.title, textValue(source.documentId, 'Untitled source')) }}</strong>
                <small v-if="sourceMeta(source)">{{ sourceMeta(source) }}</small>
              </div>
              <p>{{ textValue(source.evidenceText, 'No evidence text') }}</p>
            </li>
          </ol>
        </section>
      </div>

      <h3>Reasoning Path</h3>
      <p v-if="response.reasoningPath.length === 0">
        No reasoning path returned.
      </p>
      <div
        v-else
        class="path-groups"
      >
        <section
          v-for="group in reasoningPathGroups"
          :key="group.id"
          class="path-group"
        >
          <header class="path-group-header">
            <strong>{{ group.label }}</strong>
            <span>{{ group.pathLength }} {{ group.pathLength === 1 ? 'step' : 'steps' }}</span>
          </header>

          <ol class="path-step-list">
            <li
              v-for="step in group.steps"
              :key="`${group.id}-${String(step.evidenceId ?? step.pathStep)}`"
              class="path-step"
            >
              <span class="hop-label">{{ pathStepLabel(step) }}</span>
              <div class="relationship-line">
                <span>{{ textValue(step.source, 'Unknown source') }}</span>
                <strong>{{ textValue(step.relationship, 'RELATED_TO') }}</strong>
                <span>{{ textValue(step.target, 'Unknown target') }}</span>
              </div>
              <small v-if="evidenceMeta(step)">{{ evidenceMeta(step) }}</small>
            </li>
          </ol>
        </section>
      </div>
    </section>
  </main>
</template>

<style scoped>
.chat-page {
  display: grid;
  gap: 22px;
  max-width: 920px;
  margin: 0 auto;
  padding: 34px 24px 56px;
  text-align: left;
}

.page-header h1 {
  margin: 0 0 10px;
}

.page-header p:last-child {
  color: var(--text);
  font-size: 18px;
}

.question-panel,
.response-section {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 22px;
}

.question-panel {
  display: grid;
  gap: 12px;
}

.question-panel label {
  color: var(--text-h);
  font-size: 14px;
  font-weight: 750;
}

textarea {
  width: 100%;
  min-height: 150px;
  resize: vertical;
}

button {
  width: fit-content;
}

.response-section {
  display: grid;
  gap: 14px;
}

.response-section h2 {
  margin: 0;
}

.response-section h3 {
  margin: 10px 0 0;
  color: var(--accent);
  font-size: 14px;
  text-transform: uppercase;
}

.source-groups,
.source-list,
.path-step-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.source-group,
.path-group {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-muted);
}

.source-group {
  overflow: hidden;
}

.source-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  padding: 11px 12px;
}

.source-group-header span {
  color: var(--muted);
  font-size: 13px;
  font-weight: 750;
}

.source-list {
  gap: 0;
}

.source-item {
  display: grid;
  gap: 8px;
  padding: 12px;
}

.source-item + .source-item {
  border-top: 1px solid var(--border);
}

.source-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.source-heading small {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 12px;
  text-align: right;
}

.source-item p {
  overflow-wrap: anywhere;
}

.response-section strong {
  color: var(--text-h);
}

.path-groups {
  display: grid;
  gap: 12px;
}

.path-group {
  overflow: hidden;
}

.path-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  padding: 11px 12px;
}

.path-group-header span {
  color: var(--muted);
  font-size: 13px;
  font-weight: 750;
}

.path-step-list {
  gap: 0;
}

.path-step {
  display: grid;
  gap: 7px;
  padding: 12px;
}

.path-step + .path-step {
  border-top: 1px solid var(--border);
}

.hop-label {
  display: inline-flex;
  width: fit-content;
  border: 1px solid var(--accent-border);
  border-radius: 999px;
  background: var(--accent-bg);
  color: var(--text-h);
  font-size: 12px;
  font-weight: 750;
  line-height: 1;
  padding: 6px 9px;
}

.relationship-line {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.relationship-line span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.relationship-line strong {
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  background: var(--surface);
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.2;
  padding: 6px 8px;
  text-align: center;
}

.path-step small {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 12px;
  overflow-wrap: anywhere;
}

@media (max-width: 620px) {
  .chat-page {
    padding: 24px 16px 42px;
  }

  .source-heading,
  .source-group-header,
  .path-group-header,
  .relationship-line {
    align-items: stretch;
    grid-template-columns: 1fr;
  }

  .source-heading,
  .source-group-header,
  .path-group-header {
    flex-direction: column;
  }

  .source-heading small {
    text-align: left;
  }
}
</style>
