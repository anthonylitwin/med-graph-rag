<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getSampleGraph, type GraphResponse } from '../lib/apiClient'

const graph = ref<GraphResponse | null>(null)
const error = ref<string | null>(null)

const rawGraph = computed(() => JSON.stringify(graph.value, null, 2))

async function loadGraph() {
  try {
    error.value = null
    graph.value = await getSampleGraph()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unknown error'
  }
}

onMounted(() => {
  void loadGraph()
})
</script>

<template>
  <main class="graph-page">
    <h1>Sample Biomedical Graph</h1>

    <button @click="loadGraph">
      Refresh Graph
    </button>

    <p
      v-if="error"
      class="error"
    >
      Error: {{ error }}
    </p>

    <template v-if="graph">
      <section>
        <h2>Nodes</h2>
        <ul>
          <li
            v-for="node in graph.nodes"
            :key="node.id"
          >
            <strong>{{ node.labels.join(', ') }}</strong>:
            {{ String(node.properties.name ?? node.properties.title ?? node.id) }}
          </li>
        </ul>
      </section>

      <section>
        <h2>Relationships</h2>
        <ul>
          <li
            v-for="(relationship, index) in graph.relationships"
            :key="`${relationship.source}-${relationship.type}-${relationship.target}-${index}`"
          >
            {{ relationship.source }} --
            <strong>{{ relationship.type }}</strong>
            --&gt; {{ relationship.target }}
          </li>
        </ul>
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
  max-width: 1000px;
  margin: 2rem auto;
  font-family: sans-serif;
  text-align: left;
}

.error {
  color: red;
}

section {
  margin-top: 2rem;
}

pre {
  background: #f5f5f5;
  padding: 1rem;
  overflow: auto;
}
</style>
