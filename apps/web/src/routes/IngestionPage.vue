<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  createIngestionJob,
  getIngestionArtifacts,
  getIngestionJob,
  getIngestionModelOptions,
  listIngestionJobs,
  type IngestionArtifacts,
  type IngestionJob,
  type IngestionModelProfile,
} from '../lib/apiClient'

const sourceType = ref<'pmc' | 'text'>('pmc')
const pmcidText = ref('')
const textTitle = ref('')
const textBody = ref('')
const selectedModelProfile = ref('local-non-instruct')
const applySchema = ref(true)
const skipLoad = ref(false)
const failFast = ref(false)

const jobs = ref<IngestionJob[]>([])
const selectedJob = ref<IngestionJob | null>(null)
const artifacts = ref<IngestionArtifacts | null>(null)
const modelProfiles = ref<IngestionModelProfile[]>([])
const isSubmitting = ref(false)
const isRefreshing = ref(false)
const error = ref<string | null>(null)
let pollHandle: number | null = null

const activeJobCount = computed(() =>
  jobs.value.filter((job) => job.status === 'queued' || job.status === 'running').length
)

const selectedProgress = computed(() => {
  if (!selectedJob.value || selectedJob.value.progressTotal === 0) {
    return 0
  }
  return Math.round((selectedJob.value.progressCurrent / selectedJob.value.progressTotal) * 100)
})

function statusClass(status: string) {
  return `status status-${status}`
}

function formatDate(value?: string | null) {
  if (!value) {
    return '-'
  }
  return new Date(value).toLocaleString()
}

function formatBytes(value: number) {
  if (value < 1024) {
    return `${value} B`
  }
  if (value < 1024 * 1024) {
    return `${Math.round(value / 1024)} KB`
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

async function readFileText(event: Event, target: 'pmc' | 'text') {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) {
    return
  }
  const contents = await file.text()
  if (target === 'pmc') {
    pmcidText.value = contents
  } else {
    textTitle.value = textTitle.value || file.name.replace(/\.txt$/i, '')
    textBody.value = contents
  }
  input.value = ''
}

async function refreshJobs() {
  isRefreshing.value = true
  try {
    error.value = null
    jobs.value = await listIngestionJobs()
    if (selectedJob.value) {
      selectedJob.value = await getIngestionJob(selectedJob.value.id)
    } else if (jobs.value.length > 0) {
      selectedJob.value = await getIngestionJob(jobs.value[0].id)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown ingestion error'
  } finally {
    isRefreshing.value = false
  }
}

async function loadJob(jobId: string) {
  try {
    error.value = null
    selectedJob.value = await getIngestionJob(jobId)
    artifacts.value = null
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown ingestion error'
  }
}

async function loadArtifacts() {
  if (!selectedJob.value) {
    return
  }
  try {
    error.value = null
    artifacts.value = await getIngestionArtifacts(selectedJob.value.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown artifact error'
  }
}

async function submitJob() {
  isSubmitting.value = true
  try {
    error.value = null
    const job = await createIngestionJob({
      sourceType: sourceType.value,
      pmcidText: sourceType.value === 'pmc' ? pmcidText.value : undefined,
      documents:
        sourceType.value === 'text'
          ? [{ title: textTitle.value, text: textBody.value, sourceName: textTitle.value }]
          : undefined,
      modelProfile: selectedModelProfile.value,
      applySchema: applySchema.value,
      skipLoad: skipLoad.value,
      failFast: failFast.value,
    })
    selectedJob.value = await getIngestionJob(job.id)
    artifacts.value = null
    await refreshJobs()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown ingestion error'
  } finally {
    isSubmitting.value = false
  }
}

async function loadModelProfiles() {
  modelProfiles.value = await getIngestionModelOptions()
  if (!modelProfiles.value.some((profile) => profile.name === selectedModelProfile.value)) {
    selectedModelProfile.value = modelProfiles.value[0]?.name ?? 'noop'
  }
}

onMounted(() => {
  void loadModelProfiles().catch((err) => {
    error.value = err instanceof Error ? err.message : 'Unknown model option error'
  })
  void refreshJobs()
  pollHandle = window.setInterval(() => {
    void refreshJobs()
  }, activeJobCount.value > 0 ? 2000 : 8000)
})

onBeforeUnmount(() => {
  if (pollHandle !== null) {
    window.clearInterval(pollHandle)
  }
})
</script>

<template>
  <main class="ingestion-page">
    <header class="page-header">
      <div>
        <h1>Ingestion</h1>
        <p>Queue source documents for graph extraction and loading.</p>
      </div>

      <button
        type="button"
        :disabled="isRefreshing"
        @click="refreshJobs"
      >
        {{ isRefreshing ? 'Refreshing' : 'Refresh' }}
      </button>
    </header>

    <p
      v-if="error"
      class="error"
    >
      {{ error }}
    </p>

    <section class="submit-panel">
      <div class="segmented-control">
        <button
          type="button"
          :class="{ active: sourceType === 'pmc' }"
          @click="sourceType = 'pmc'"
        >
          PMC IDs
        </button>
        <button
          type="button"
          :class="{ active: sourceType === 'text' }"
          @click="sourceType = 'text'"
        >
          Text
        </button>
      </div>

      <div
        v-if="sourceType === 'pmc'"
        class="input-stack"
      >
        <label for="pmcids">PMC IDs</label>
        <textarea
          id="pmcids"
          v-model="pmcidText"
          rows="6"
          placeholder="PMC3572442&#10;PMC3234107"
        />
        <label class="file-input">
          <span>Load .txt file</span>
          <input
            type="file"
            accept=".txt,text/plain"
            @change="readFileText($event, 'pmc')"
          >
        </label>
      </div>

      <div
        v-else
        class="input-stack"
      >
        <label for="text-title">Title</label>
        <input
          id="text-title"
          v-model="textTitle"
          type="text"
          placeholder="Article title"
        >

        <label for="text-body">Text</label>
        <textarea
          id="text-body"
          v-model="textBody"
          rows="10"
          placeholder="Paste the full text to ingest"
        />
        <label class="file-input">
          <span>Load .txt file</span>
          <input
            type="file"
            accept=".txt,text/plain"
            @change="readFileText($event, 'text')"
          >
        </label>
      </div>

      <div class="options-grid">
        <label>
          Model
          <select v-model="selectedModelProfile">
            <option
              v-for="profile in modelProfiles"
              :key="profile.name"
              :value="profile.name"
            >
              {{ profile.label }}
            </option>
          </select>
        </label>

        <label class="checkbox-label">
          <input
            v-model="applySchema"
            type="checkbox"
          >
          Apply schema
        </label>

        <label class="checkbox-label">
          <input
            v-model="skipLoad"
            type="checkbox"
          >
          Skip Neo4j load
        </label>

        <label class="checkbox-label">
          <input
            v-model="failFast"
            type="checkbox"
          >
          Fail fast
        </label>
      </div>

      <button
        type="button"
        class="primary-button"
        :disabled="isSubmitting"
        @click="submitJob"
      >
        {{ isSubmitting ? 'Queueing' : 'Queue Job' }}
      </button>
    </section>

    <section class="queue-layout">
      <div class="queue-list">
        <div class="section-header">
          <h2>Queue</h2>
          <span>{{ activeJobCount }} active</span>
        </div>

        <table>
          <thead>
            <tr>
              <th>Job</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Source</th>
              <th>Submitted</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="job in jobs"
              :key="job.id"
              :class="{ selected: selectedJob?.id === job.id }"
              @click="loadJob(job.id)"
            >
              <td>{{ job.id }}</td>
              <td>
                <span :class="statusClass(job.status)">
                  {{ job.status }}
                </span>
              </td>
              <td>{{ job.progressCurrent }} / {{ job.progressTotal }}</td>
              <td>{{ job.sourceType }}</td>
              <td>{{ formatDate(job.submittedAt) }}</td>
            </tr>
          </tbody>
        </table>

        <p
          v-if="jobs.length === 0"
          class="empty"
        >
          No ingestion jobs yet.
        </p>
      </div>

      <aside
        v-if="selectedJob"
        class="job-detail"
      >
        <div class="section-header">
          <h2>{{ selectedJob.id }}</h2>
          <span :class="statusClass(selectedJob.status)">
            {{ selectedJob.status }}
          </span>
        </div>

        <div class="progress-track">
          <div
            class="progress-fill"
            :style="{ width: `${selectedProgress}%` }"
          />
        </div>

        <dl>
          <div>
            <dt>Model</dt>
            <dd>{{ selectedJob.modelProfile }}</dd>
          </div>
          <div>
            <dt>Output</dt>
            <dd>{{ selectedJob.outputRoot }}</dd>
          </div>
          <div>
            <dt>Started</dt>
            <dd>{{ formatDate(selectedJob.startedAt) }}</dd>
          </div>
          <div>
            <dt>Finished</dt>
            <dd>{{ formatDate(selectedJob.finishedAt) }}</dd>
          </div>
        </dl>

        <p
          v-if="selectedJob.error"
          class="error"
        >
          {{ selectedJob.error }}
        </p>

        <h3>Documents</h3>
        <table class="document-table">
          <thead>
            <tr>
              <th>Document</th>
              <th>Status</th>
              <th>Chunks</th>
              <th>Entities</th>
              <th>Rels</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="document in selectedJob.documents"
              :key="document.documentKey"
            >
              <td>
                <strong>{{ document.title || document.documentKey }}</strong>
                <span v-if="document.error">{{ document.error }}</span>
              </td>
              <td>
                <span :class="statusClass(document.status)">
                  {{ document.status }}
                </span>
              </td>
              <td>{{ document.chunkCount }}</td>
              <td>{{ document.entityCount }}</td>
              <td>{{ document.relationshipCount }}</td>
            </tr>
          </tbody>
        </table>

        <button
          type="button"
          @click="loadArtifacts"
        >
          Show Artifacts
        </button>

        <ul
          v-if="artifacts"
          class="artifact-list"
        >
          <li
            v-for="file in artifacts.files"
            :key="file.relativePath"
          >
            <code>{{ file.relativePath }}</code>
            <span>{{ formatBytes(file.size) }}</span>
          </li>
        </ul>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.ingestion-page {
  max-width: 1080px;
  margin: 2rem auto;
  padding: 0 1rem 3rem;
  font-family: sans-serif;
  text-align: left;
}

.page-header,
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.page-header p,
.empty,
dt {
  color: #6b7280;
}

.submit-panel {
  border-block: 1px solid #e5e7eb;
  margin-top: 1.5rem;
  padding: 1.25rem 0;
}

.segmented-control {
  display: inline-flex;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 1rem;
}

.segmented-control button {
  border: 0;
  border-radius: 0;
  margin: 0;
  padding: 0.55rem 0.9rem;
}

.segmented-control .active {
  background: #111827;
  color: #fff;
}

.input-stack {
  display: grid;
  gap: 0.5rem;
}

textarea,
input[type='text'],
select {
  box-sizing: border-box;
  width: 100%;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  padding: 0.75rem;
  font: inherit;
}

.file-input {
  width: fit-content;
  cursor: pointer;
}

.file-input input {
  display: none;
}

.file-input span,
button {
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  color: #111827;
  padding: 0.55rem 0.8rem;
  font: inherit;
  cursor: pointer;
}

.options-grid {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) repeat(3, max-content);
  gap: 1rem;
  align-items: end;
  margin-top: 1rem;
}

.checkbox-label {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
  white-space: nowrap;
}

.primary-button {
  margin-top: 1rem;
  background: #0f766e;
  border-color: #0f766e;
  color: #fff;
}

button:disabled {
  cursor: wait;
  opacity: 0.65;
}

.queue-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.9fr);
  gap: 1.25rem;
  margin-top: 1.5rem;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92rem;
}

th,
td {
  border-bottom: 1px solid #e5e7eb;
  padding: 0.65rem 0.5rem;
  vertical-align: top;
}

th {
  color: #4b5563;
  font-weight: 600;
}

tbody tr {
  cursor: pointer;
}

tbody tr.selected,
tbody tr:hover {
  background: #f9fafb;
}

.job-detail {
  border-left: 1px solid #e5e7eb;
  padding-left: 1.25rem;
}

.progress-track {
  height: 10px;
  border-radius: 999px;
  background: #e5e7eb;
  overflow: hidden;
  margin: 1rem 0;
}

.progress-fill {
  height: 100%;
  background: #0f766e;
  transition: width 160ms ease;
}

dl {
  display: grid;
  gap: 0.75rem;
}

dl div {
  display: grid;
  gap: 0.15rem;
}

dd {
  margin: 0;
  overflow-wrap: anywhere;
}

h3 {
  margin: 1.5rem 0 0.5rem;
}

.document-table td:first-child {
  overflow-wrap: anywhere;
}

.document-table span {
  display: block;
  color: #b91c1c;
  font-size: 0.84rem;
}

.status {
  display: inline-flex;
  border-radius: 999px;
  padding: 0.15rem 0.5rem;
  background: #f3f4f6;
  color: #374151;
  font-size: 0.82rem;
  line-height: 1.4;
}

.status-running,
.status-queued {
  background: #dbeafe;
  color: #1d4ed8;
}

.status-completed,
.status-ok {
  background: #dcfce7;
  color: #166534;
}

.status-failed,
.status-error {
  background: #fee2e2;
  color: #991b1b;
}

.status-skipped,
.status-canceled {
  background: #fef3c7;
  color: #92400e;
}

.error {
  color: #b91c1c;
  margin-top: 1rem;
}

.artifact-list {
  list-style: none;
  padding: 0;
}

.artifact-list li {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid #e5e7eb;
  padding: 0.45rem 0;
}

@media (max-width: 860px) {
  .page-header,
  .section-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .options-grid,
  .queue-layout {
    grid-template-columns: 1fr;
  }

  .job-detail {
    border-left: 0;
    border-top: 1px solid #e5e7eb;
    padding-left: 0;
    padding-top: 1rem;
  }
}
</style>
