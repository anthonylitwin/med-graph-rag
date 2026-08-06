<script setup lang="ts">
import { ref } from 'vue'
import { sendChatMessage, type ChatResponse } from '../lib/apiClient'

const message = ref('')
const response = ref<ChatResponse | null>(null)
const isLoading = ref(false)

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
      <ul v-else>
        <li
          v-for="(source, index) in response.sources"
          :key="index"
        >
          <strong>{{ String(source.title ?? 'Untitled source') }}</strong>
          <br>
          <span>{{ String(source.evidenceText ?? 'No evidence text') }}</span>
        </li>
      </ul>

      <h3>Reasoning Path</h3>
      <p v-if="response.reasoningPath.length === 0">
        No reasoning path returned.
      </p>
      <ul v-else>
        <li
          v-for="(step, index) in response.reasoningPath"
          :key="index"
        >
          {{ String(step.source) }} --
          <strong>{{ String(step.relationship) }}</strong>
          --&gt; {{ String(step.target) }}
        </li>
      </ul>
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

.response-section ul {
  display: grid;
  gap: 10px;
  margin: 0;
  padding-left: 20px;
}

.response-section li {
  padding-left: 4px;
}

.response-section strong {
  color: var(--text-h);
}

@media (max-width: 620px) {
  .chat-page {
    padding: 24px 16px 42px;
  }
}
</style>
