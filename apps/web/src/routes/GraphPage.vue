<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import GraphCanvas, { type GraphSelection } from '../components/GraphCanvas.vue'
import {
  browseGraph,
  getSampleGraph,
  type GraphBrowseParams,
  type GraphNode,
  type GraphRelationship,
  type GraphResponse,
} from '../lib/apiClient'

const NODE_LABELS = ['Paper', 'Drug', 'Condition', 'Symptom', 'RiskFactor', 'Biomarker']
const RELATIONSHIP_TYPES = [
  'MENTIONS',
  'TREATS',
  'PREVENTS',
  'REDUCES',
  'INCREASES',
  'ASSOCIATED_WITH',
  'HAS_ADVERSE_EFFECT',
  'CAUSES',
  'HAS_SYMPTOM',
  'INCREASES_RISK_OF',
  'INTERACTS_WITH',
  'CONTRAINDICATED_FOR',
  'MAY_INTERACT_WITH',
  'MAY_INCREASE_RISK_OF',
  'MAY_REDUCE',
]

const graph = ref<GraphResponse | null>(null)
const error = ref<string | null>(null)
const loading = ref(false)
const activeMode = ref<'browse' | 'sample'>('browse')
const selectedItem = ref<GraphSelection | null>(null)

const filters = reactive({
  q: '',
  label: '',
  relationshipType: '',
  pmcid: '',
  limit: 50,
})

const rawGraph = computed(() => JSON.stringify(graph.value, null, 2))
const hasGraph = computed(() => Boolean(graph.value?.nodes.length || graph.value?.relationships.length))
const nodeCount = computed(() => graph.value?.metadata?.nodeCount ?? graph.value?.nodes.length ?? 0)
const relationshipCount = computed(
  () => graph.value?.metadata?.relationshipCount ?? graph.value?.relationships.length ?? 0,
)
const selectedProperties = computed(() => Object.entries(selectedItem.value?.properties ?? {}))

function cleanParams(): GraphBrowseParams {
  return {
    q: filters.q.trim() || undefined,
    label: filters.label || undefined,
    relationshipType: filters.relationshipType || undefined,
    pmcid: filters.pmcid.trim() || undefined,
    limit: filters.limit,
  }
}

async function runGraphRequest(request: () => Promise<GraphResponse>, mode: 'browse' | 'sample') {
  try {
    loading.value = true
    error.value = null
    graph.value = await request()
    activeMode.value = mode
    selectedItem.value = null
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown error'
  } finally {
    loading.value = false
  }
}

async function browse() {
  await runGraphRequest(() => browseGraph(cleanParams()), 'browse')
}

async function loadSample() {
  await runGraphRequest(getSampleGraph, 'sample')
}

function resetFilters() {
  filters.q = ''
  filters.label = ''
  filters.relationshipType = ''
  filters.pmcid = ''
  filters.limit = 50
  void browse()
}

function nodeTitle(node: GraphNode): string {
  const value = node.properties.name ?? node.properties.title ?? node.properties.pmcid ?? node.properties.id
  return value ? String(value) : node.id
}

function nodeSubtitle(node: GraphNode): string {
  return node.labels.join(', ')
}

function nodeLookup(graphResponse: GraphResponse | null): Map<string, GraphNode> {
  return new Map((graphResponse?.nodes ?? []).map((node) => [node.id, node]))
}

function relationshipEndpoint(id: string): string {
  const node = nodeLookup(graph.value).get(id)
  return node ? nodeTitle(node) : id
}

function relationshipEvidence(relationship: GraphRelationship): string {
  const evidence = relationship.properties.evidence ?? relationship.properties.source_pmcid ?? relationship.properties.id
  return evidence ? String(evidence) : ''
}

function propertyValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.join(', ')
  }

  if (value && typeof value === 'object') {
    return JSON.stringify(value)
  }

  return value === undefined || value === null ? '' : String(value)
}

onMounted(() => {
  void browse()
})
</script>

<template>
  <main class="graph-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">
          Graph
        </p>
        <h1>Biomedical Explorer</h1>
      </div>

      <div class="summary-strip">
        <span>{{ nodeCount }} nodes</span>
        <span>{{ relationshipCount }} relationships</span>
      </div>
    </header>

    <form
      class="graph-controls"
      @submit.prevent="browse"
    >
      <label class="search-field">
        <span>Search</span>
        <input
          v-model="filters.q"
          name="q"
          placeholder="Aspirin, inflammation, PMC3572442"
          type="search"
        >
      </label>

      <label>
        <span>Label</span>
        <select
          v-model="filters.label"
          name="label"
        >
          <option value="">
            Any
          </option>
          <option
            v-for="label in NODE_LABELS"
            :key="label"
            :value="label"
          >
            {{ label }}
          </option>
        </select>
      </label>

      <label>
        <span>Relation</span>
        <select
          v-model="filters.relationshipType"
          name="relationshipType"
        >
          <option value="">
            Any
          </option>
          <option
            v-for="relationshipType in RELATIONSHIP_TYPES"
            :key="relationshipType"
            :value="relationshipType"
          >
            {{ relationshipType }}
          </option>
        </select>
      </label>

      <label>
        <span>PMCID</span>
        <input
          v-model="filters.pmcid"
          name="pmcid"
          placeholder="PMC3572442"
        >
      </label>

      <label class="limit-field">
        <span>Limit</span>
        <input
          v-model.number="filters.limit"
          max="100"
          min="1"
          name="limit"
          type="number"
        >
      </label>

      <div class="button-row">
        <button
          :disabled="loading"
          type="submit"
        >
          Browse
        </button>
        <button
          :disabled="loading"
          type="button"
          @click="loadSample"
        >
          Sample
        </button>
        <button
          :disabled="loading"
          type="button"
          @click="resetFilters"
        >
          Reset
        </button>
      </div>
    </form>

    <p
      v-if="error"
      class="error"
    >
      Error: {{ error }}
    </p>

    <p
      v-else-if="loading"
      class="status"
    >
      Loading graph...
    </p>

    <p
      v-else-if="graph && !hasGraph"
      class="status"
    >
      No matching graph records.
    </p>

    <template v-if="graph && hasGraph">
      <section class="results-header">
        <h2>
          {{ activeMode === 'sample' ? 'Sample Graph' : 'Browse Results' }}
        </h2>
        <p>
          {{ nodeCount }} nodes and {{ relationshipCount }} relationships
        </p>
      </section>

      <section class="visual-grid">
        <GraphCanvas
          :nodes="graph.nodes"
          :relationships="graph.relationships"
          @select="selectedItem = $event"
        />

        <aside class="inspector">
          <template v-if="selectedItem">
            <p class="eyebrow">
              {{ selectedItem.kind === 'node' ? 'Node' : 'Relationship' }}
            </p>
            <h2>
              {{ selectedItem.kind === 'node' ? selectedItem.title : selectedItem.type }}
            </h2>
            <p
              v-if="selectedItem.kind === 'relationship'"
              class="endpoint-line"
            >
              {{ selectedItem.source }} -> {{ selectedItem.target }}
            </p>
            <p
              v-else
              class="endpoint-line"
            >
              {{ selectedItem.labels.join(', ') }}
            </p>

            <dl v-if="selectedProperties.length">
              <template
                v-for="[key, value] in selectedProperties"
                :key="key"
              >
                <dt>{{ key }}</dt>
                <dd>{{ propertyValue(value) }}</dd>
              </template>
            </dl>
          </template>

          <template v-else>
            <p class="eyebrow">
              Inspector
            </p>
            <h2>Nothing Selected</h2>
            <p class="endpoint-line">
              Select a node or relationship in the graph.
            </p>
          </template>
        </aside>
      </section>

      <section class="result-grid">
        <div>
          <h2>Nodes</h2>
          <ul class="node-list">
            <li
              v-for="node in graph.nodes"
              :key="node.id"
            >
              <strong>{{ nodeTitle(node) }}</strong>
              <span>{{ nodeSubtitle(node) }}</span>
              <code>{{ String(node.properties.pmcid ?? node.properties.id ?? node.id) }}</code>
            </li>
          </ul>
        </div>

        <div>
          <h2>Relationships</h2>
          <ul class="relationship-list">
            <li
              v-for="(relationship, index) in graph.relationships"
              :key="`${relationship.source}-${relationship.type}-${relationship.target}-${index}`"
            >
              <span>{{ relationshipEndpoint(relationship.source) }}</span>
              <strong>{{ relationship.type }}</strong>
              <span>{{ relationshipEndpoint(relationship.target) }}</span>
              <small v-if="relationshipEvidence(relationship)">
                {{ relationshipEvidence(relationship) }}
              </small>
            </li>
          </ul>
        </div>
      </section>

      <section>
        <h2>Raw Graph JSON</h2>
        <pre>{{ rawGraph }}</pre>
      </section>
    </template>
  </main>
</template>

<style scoped>
.graph-page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 32px 24px 48px;
  text-align: left;
}

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.page-header h1 {
  margin: 0;
  font-size: 42px;
  line-height: 1.1;
  letter-spacing: 0;
}

.eyebrow {
  margin-bottom: 6px;
  color: #25636f;
  font-size: 14px;
  font-weight: 700;
  text-transform: uppercase;
}

.summary-strip {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.summary-strip span {
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-h);
  font-size: 14px;
  padding: 6px 10px;
}

.graph-controls {
  display: grid;
  grid-template-columns: minmax(220px, 2fr) minmax(130px, 1fr) minmax(180px, 1fr) minmax(
      150px,
      1fr
    ) 90px;
  gap: 14px;
  align-items: end;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg) 88%, #f1f5f9);
}

label {
  display: grid;
  gap: 6px;
  color: var(--text-h);
  font-size: 14px;
  font-weight: 600;
}

input,
select {
  width: 100%;
  min-height: 40px;
  box-sizing: border-box;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-h);
  font: inherit;
  font-size: 15px;
  padding: 8px 10px;
}

.button-row {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

button {
  min-height: 40px;
  border: 1px solid #25636f;
  border-radius: 6px;
  background: #25636f;
  color: #fff;
  cursor: pointer;
  font: inherit;
  font-size: 15px;
  font-weight: 700;
  padding: 8px 14px;
}

button[type='button'] {
  background: var(--bg);
  color: #25636f;
}

button:disabled {
  cursor: progress;
  opacity: 0.65;
}

.error,
.status {
  margin-top: 18px;
  border-radius: 6px;
  padding: 12px 14px;
}

.error {
  border: 1px solid #f3b5b5;
  background: #fff1f1;
  color: #a01818;
}

.status {
  border: 1px solid var(--border);
  color: var(--text-h);
}

.results-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: baseline;
  margin: 28px 0 16px;
}

.results-header h2,
.results-header p {
  margin: 0;
}

.visual-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 18px;
  align-items: stretch;
}

.inspector {
  min-height: 560px;
  box-sizing: border-box;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  padding: 16px;
}

.inspector h2 {
  overflow-wrap: anywhere;
}

.endpoint-line {
  color: var(--text);
  font-size: 14px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

dl {
  display: grid;
  gap: 8px;
  margin: 18px 0 0;
}

dt {
  color: var(--text-h);
  font-size: 13px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

dd {
  margin: -4px 0 6px;
  color: var(--text);
  font-size: 13px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.result-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.25fr);
  gap: 24px;
}

.node-list,
.relationship-list {
  display: grid;
  gap: 10px;
  list-style: none;
  margin: 0;
  padding: 0;
}

.node-list li,
.relationship-list li {
  display: grid;
  gap: 5px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}

.node-list strong,
.relationship-list strong {
  color: var(--text-h);
}

.node-list span,
.relationship-list small {
  color: var(--text);
  font-size: 14px;
}

.relationship-list strong {
  color: #25636f;
  font-size: 13px;
}

section {
  margin-top: 24px;
}

pre {
  max-height: 420px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--code-bg);
  color: var(--text-h);
  padding: 16px;
}

@media (max-width: 860px) {
  .page-header,
  .results-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .summary-strip {
    justify-content: flex-start;
  }

  .graph-controls,
  .visual-grid,
  .result-grid {
    grid-template-columns: 1fr;
  }

  .inspector {
    min-height: 240px;
  }
}
</style>
