<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  getChatModelOptions,
  sendChatMessage,
  type ChatResponse,
  type ModelOption,
} from '../lib/apiClient'

const FALLBACK_MODEL_OPTIONS: ModelOption[] = [
  {
    name: 'frontier',
    label: 'Frontier API',
    description: 'Configured OpenAI frontier runtime.',
    qa_provider: 'openai',
    qa_model: 'gpt-5.5',
    qa_retriever: 'graph',
    extractor_provider: 'openai',
    extractor_model: 'gpt-5.5',
    entity_model: '',
  },
  {
    name: 'local-qwen25',
    label: 'Local Qwen 2.5',
    description: 'Ollama qwen2.5:7b-instruct runtime.',
    qa_provider: 'ollama',
    qa_model: 'qwen2.5:7b-instruct',
    qa_retriever: 'graph',
    extractor_provider: 'gliner_ollama',
    extractor_model: 'qwen2.5:7b-instruct',
    entity_model: 'Ihor/gliner-biomed-small-v1.0',
  },
  {
    name: 'local-qwen3',
    label: 'Local Qwen 3',
    description: 'Ollama qwen3:8b runtime.',
    qa_provider: 'ollama',
    qa_model: 'qwen3:8b',
    qa_retriever: 'graph',
    extractor_provider: 'gliner_ollama',
    extractor_model: 'qwen3:8b',
    entity_model: 'Ihor/gliner-biomed-small-v1.0',
  },
  {
    name: 'local-gliner',
    label: 'Local GLiNER (non-instruct extraction)',
    description: 'Ollama QA with non-generative GLiNER-BioMed entity extraction.',
    qa_provider: 'ollama',
    qa_model: 'qwen2.5:7b-instruct',
    qa_retriever: 'graph',
    extractor_provider: 'gliner',
    extractor_model: 'Ihor/gliner-biomed-small-v1.0',
    entity_model: 'Ihor/gliner-biomed-small-v1.0',
  },
  {
    name: 'local-non-instruct',
    label: 'Local non-instruct pipeline',
    description: 'GLiNER entities with terminology normalization and cosine-scored relationships.',
    qa_provider: 'ollama',
    qa_model: 'qwen2.5:7b-instruct',
    qa_retriever: 'graph',
    extractor_provider: 'non_instruct',
    extractor_model: 'sentence-transformers/all-MiniLM-L6-v2',
    entity_model: 'Ihor/gliner-biomed-small-v1.0',
  },
  {
    name: 'noop',
    label: 'Noop',
    description: 'Deterministic smoke-test runtime.',
    qa_provider: 'noop',
    qa_model: 'noop-language-model-v0',
    qa_retriever: 'noop',
    extractor_provider: 'noop',
    extractor_model: 'noop-extractor-v0',
    entity_model: '',
  },
]

const message = ref('')
const modelProfile = ref('frontier')
const modelOptions = ref<ModelOption[]>(FALLBACK_MODEL_OPTIONS)
const response = ref<ChatResponse | null>(null)
const isLoading = ref(false)

onMounted(async () => {
  try {
    const options = await getChatModelOptions()
    modelOptions.value = options.profiles
    modelProfile.value = options.defaultProfile
  } catch {
    modelOptions.value = FALLBACK_MODEL_OPTIONS
  }
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
      modelProfile: modelProfile.value,
    })
  } catch (error) {
    response.value = {
      answer: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
      sources: [],
      reasoningPath: [],
      model: 'error',
      provider: 'error',
      modelProfile: modelProfile.value,
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
      <div class="model-row">
        <label for="model-profile">Model</label>
        <select
          id="model-profile"
          v-model="modelProfile"
        >
          <option
            v-for="option in modelOptions"
            :key="option.name"
            :value="option.name"
          >
            {{ option.label }}
          </option>
        </select>
      </div>

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

.model-row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 1rem;
}

select {
  min-width: 220px;
  padding: 0.5rem;
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
