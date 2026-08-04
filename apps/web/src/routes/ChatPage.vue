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
    <h1>MedGraphRAG</h1>
    <p>Ask a biomedical question against the configured graph evidence.</p>

    <form @submit.prevent="handleSubmit">
      <textarea
        v-model="message"
        rows="5"
        placeholder="Ask a question..."
      />

      <button
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
  max-width: 900px;
  margin: 2rem auto;
  font-family: sans-serif;
  text-align: left;
}

textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 1rem;
}

button {
  margin-top: 1rem;
}

.response-section {
  margin-top: 2rem;
}
</style>
