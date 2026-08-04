<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  clearAdminNeo4j,
  getAdminNeo4jStatus,
  type AdminNeo4jClearResponse,
  type AdminNeo4jStatus,
} from '../lib/apiClient'

const status = ref<AdminNeo4jStatus | null>(null)
const lastClear = ref<AdminNeo4jClearResponse | null>(null)
const confirmationText = ref('')
const isLoading = ref(false)
const isClearing = ref(false)
const error = ref<string | null>(null)

const canSubmitClear = computed(
  () => status.value?.canClear === true && confirmationText.value === 'CLEAR' && !isClearing.value,
)

function formatDate(value: string) {
  return new Date(value).toLocaleString()
}

async function refreshStatus() {
  isLoading.value = true
  try {
    error.value = null
    status.value = await getAdminNeo4jStatus()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown administration error'
  } finally {
    isLoading.value = false
  }
}

async function clearNeo4j() {
  if (!canSubmitClear.value) {
    return
  }

  isClearing.value = true
  try {
    error.value = null
    lastClear.value = await clearAdminNeo4j({ confirmation: confirmationText.value })
    confirmationText.value = ''
    await refreshStatus()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown Neo4j clear error'
  } finally {
    isClearing.value = false
  }
}

onMounted(() => {
  void refreshStatus()
})
</script>

<template>
  <main class="administration-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">
          Administration
        </p>
        <h1>Neo4j Controls</h1>
      </div>

      <button
        type="button"
        :disabled="isLoading"
        @click="refreshStatus"
      >
        {{ isLoading ? 'Refreshing' : 'Refresh' }}
      </button>
    </header>

    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>

    <section class="status-grid">
      <div class="metric">
        <span>Nodes</span>
        <strong>{{ status?.nodeCount ?? '-' }}</strong>
      </div>
      <div class="metric">
        <span>Relationships</span>
        <strong>{{ status?.relationshipCount ?? '-' }}</strong>
      </div>
      <div class="metric">
        <span>Active ingestion</span>
        <strong>{{ status?.activeIngestionJobs.length ?? '-' }}</strong>
      </div>
    </section>

    <section class="danger-zone">
      <div class="section-header">
        <div>
          <h2>Clear Neo4j Database</h2>
          <p>Deletes all graph nodes and relationships while preserving Neo4j schema.</p>
        </div>
      </div>

      <p
        v-if="status && !status.canClear"
        class="blocked"
      >
        Clearing is disabled while ingestion jobs are queued or running.
      </p>

      <ul
        v-if="status?.activeIngestionJobs.length"
        class="job-list"
      >
        <li
          v-for="job in status.activeIngestionJobs"
          :key="job.id"
        >
          <strong>{{ job.id }}</strong>
          <span>{{ job.status }} · {{ job.sourceType }} · {{ formatDate(job.submittedAt) }}</span>
        </li>
      </ul>

      <label class="confirmation-field">
        <span>Type CLEAR to enable deletion</span>
        <input
          v-model="confirmationText"
          autocomplete="off"
          spellcheck="false"
          type="text"
        >
      </label>

      <button
        class="danger-button"
        type="button"
        :disabled="!canSubmitClear"
        @click="clearNeo4j"
      >
        {{ isClearing ? 'Clearing' : 'Clear Neo4j' }}
      </button>

      <p
        v-if="lastClear"
        class="success"
      >
        Cleared {{ lastClear.deletedNodeCount }} nodes. Neo4j now has {{ lastClear.after.nodeCount }} nodes and
        {{ lastClear.after.relationshipCount }} relationships.
      </p>
    </section>
  </main>
</template>

<style scoped>
.administration-page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 32px 24px 48px;
  text-align: left;
}

.page-header,
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-header {
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

button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 28px;
}

.metric {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}

.metric span {
  display: block;
  color: var(--text);
  font-size: 14px;
}

.metric strong {
  color: var(--text-h);
  display: block;
  font-size: 30px;
  line-height: 1.2;
  margin-top: 6px;
}

.danger-zone {
  border-block: 1px solid var(--border);
  padding: 20px 0;
}

.danger-zone h2,
.danger-zone p {
  margin: 0;
}

.danger-zone p {
  color: var(--text);
}

.confirmation-field {
  display: grid;
  gap: 8px;
  max-width: 360px;
  margin-top: 18px;
  color: var(--text-h);
  font-size: 14px;
  font-weight: 600;
}

input {
  box-sizing: border-box;
  width: 100%;
  min-height: 40px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text-h);
  font: inherit;
  padding: 8px 10px;
}

.danger-button {
  margin-top: 14px;
  border-color: #b91c1c;
  background: #b91c1c;
}

.blocked,
.error,
.success {
  margin-top: 16px;
  border-radius: 6px;
  padding: 12px 14px;
}

.blocked {
  border: 1px solid #fde68a;
  background: #fffbeb;
  color: #92400e;
}

.error {
  border: 1px solid #f3b5b5;
  background: #fff1f1;
  color: #a01818;
}

.success {
  border: 1px solid #bbf7d0;
  background: #f0fdf4;
  color: #166534;
}

.job-list {
  display: grid;
  gap: 8px;
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
}

.job-list li {
  display: grid;
  gap: 4px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}

.job-list span {
  color: var(--text);
  font-size: 14px;
}

@media (max-width: 760px) {
  .page-header,
  .section-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
