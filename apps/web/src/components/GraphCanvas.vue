<script setup lang="ts">
import cytoscape, { type Core, type EdgeSingular, type NodeSingular } from 'cytoscape'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { GraphNode, GraphRelationship } from '../lib/apiClient'

export type GraphSelection =
  | {
      kind: 'node'
      id: string
      labels: string[]
      title: string
      properties: Record<string, unknown>
    }
  | {
      kind: 'relationship'
      id: string
      type: string
      source: string
      target: string
      properties: Record<string, unknown>
    }

const props = defineProps<{
  nodes: GraphNode[]
  relationships: GraphRelationship[]
}>()

const emit = defineEmits<{
  select: [selection: GraphSelection | null]
}>()

const container = ref<HTMLDivElement | null>(null)
const cy = ref<Core | null>(null)

const elementCount = computed(() => props.nodes.length + props.relationships.length)

function nodeTitle(node: GraphNode): string {
  const value = node.properties.name ?? node.properties.title ?? node.properties.pmcid ?? node.properties.id
  return value ? String(value) : node.id
}

function primaryLabel(node: GraphNode): string {
  return node.labels[0] ?? 'Entity'
}

function relationshipId(relationship: GraphRelationship, index: number): string {
  const id = relationship.properties.id
  return id ? String(id) : `${relationship.source}-${relationship.type}-${relationship.target}-${index}`
}

function rebuildElements() {
  if (!cy.value) {
    return
  }

  const elements = [
    ...props.nodes.map((node) => ({
      data: {
        id: node.id,
        label: nodeTitle(node),
        nodeType: primaryLabel(node),
        labels: node.labels,
        properties: node.properties,
      },
    })),
    ...props.relationships.map((relationship, index) => ({
      data: {
        id: relationshipId(relationship, index),
        source: relationship.source,
        target: relationship.target,
        label: relationship.type,
        relationshipType: relationship.type,
        properties: relationship.properties,
      },
    })),
  ]

  cy.value.elements().remove()
  cy.value.add(elements)
  runLayout()
}

function runLayout() {
  cy.value
    ?.layout({
      name: 'cose',
      animate: true,
      animationDuration: 450,
      fit: true,
      padding: 36,
      nodeRepulsion: 9000,
      idealEdgeLength: 110,
      edgeElasticity: 90,
      nestingFactor: 1.1,
      gravity: 0.25,
      numIter: 1000,
    })
    .run()
}

function fitGraph() {
  cy.value?.fit(undefined, 36)
}

function zoomGraph(multiplier: number) {
  const instance = cy.value
  if (!instance) {
    return
  }

  instance.zoom({
    level: instance.zoom() * multiplier,
    renderedPosition: {
      x: instance.width() / 2,
      y: instance.height() / 2,
    },
  })
}

function selectedNode(node: NodeSingular): GraphSelection {
  return {
    kind: 'node',
    id: node.id(),
    labels: node.data('labels') as string[],
    title: node.data('label') as string,
    properties: node.data('properties') as Record<string, unknown>,
  }
}

function selectedEdge(edge: EdgeSingular): GraphSelection {
  return {
    kind: 'relationship',
    id: edge.id(),
    type: edge.data('relationshipType') as string,
    source: edge.source().data('label') as string,
    target: edge.target().data('label') as string,
    properties: edge.data('properties') as Record<string, unknown>,
  }
}

function createGraph() {
  if (!container.value) {
    return
  }

  cy.value = cytoscape({
    container: container.value,
    minZoom: 0.25,
    maxZoom: 3,
    wheelSensitivity: 0.18,
    style: [
      {
        selector: 'node',
        style: {
          'background-color': '#64748b',
          'border-color': '#ffffff',
          'border-width': 2,
          color: '#15202b',
          'font-size': 11,
          height: 42,
          label: 'data(label)',
          'overlay-opacity': 0,
          shape: 'ellipse',
          'text-background-color': '#ffffff',
          'text-background-opacity': 0.82,
          'text-background-padding': '3px',
          'text-margin-y': -9,
          'text-max-width': '110px',
          'text-valign': 'top',
          'text-wrap': 'wrap',
          width: 42,
        },
      },
      {
        selector: 'node[nodeType = "Paper"]',
        style: {
          'background-color': '#2f6f73',
          height: 52,
          shape: 'round-rectangle',
          width: 72,
        },
      },
      {
        selector: 'node[nodeType = "Drug"]',
        style: {
          'background-color': '#c2410c',
        },
      },
      {
        selector: 'node[nodeType = "Condition"]',
        style: {
          'background-color': '#0f766e',
        },
      },
      {
        selector: 'node[nodeType = "Symptom"]',
        style: {
          'background-color': '#7c3aed',
        },
      },
      {
        selector: 'node[nodeType = "RiskFactor"]',
        style: {
          'background-color': '#be123c',
          shape: 'diamond',
        },
      },
      {
        selector: 'node[nodeType = "Biomarker"]',
        style: {
          'background-color': '#2563eb',
          shape: 'hexagon',
        },
      },
      {
        selector: 'edge',
        style: {
          color: '#475569',
          'curve-style': 'bezier',
          'font-size': 9,
          label: 'data(label)',
          'line-color': '#94a3b8',
          'overlay-opacity': 0,
          'target-arrow-color': '#94a3b8',
          'target-arrow-shape': 'triangle',
          'text-background-color': '#ffffff',
          'text-background-opacity': 0.82,
          'text-background-padding': '2px',
          'text-rotation': 'autorotate',
          width: 1.8,
        },
      },
      {
        selector: 'edge[relationshipType = "MENTIONS"]',
        style: {
          'line-color': '#cbd5e1',
          'target-arrow-color': '#cbd5e1',
          width: 1.2,
        },
      },
      {
        selector: ':selected',
        style: {
          'border-color': '#111827',
          'border-width': 4,
          'line-color': '#111827',
          'target-arrow-color': '#111827',
          width: 3,
        },
      },
    ],
  })

  cy.value.on('tap', 'node', (event) => emit('select', selectedNode(event.target)))
  cy.value.on('tap', 'edge', (event) => emit('select', selectedEdge(event.target)))
  cy.value.on('tap', (event) => {
    if (event.target === cy.value) {
      emit('select', null)
    }
  })

  rebuildElements()
}

watch(
  () => [props.nodes, props.relationships],
  () => {
    void nextTick(rebuildElements)
  },
  { deep: true },
)

onMounted(() => {
  createGraph()
})

onBeforeUnmount(() => {
  cy.value?.destroy()
  cy.value = null
})
</script>

<template>
  <div class="graph-shell">
    <div class="graph-toolbar">
      <span>{{ elementCount }} elements</span>
      <div>
        <button
          title="Zoom in"
          type="button"
          @click="zoomGraph(1.2)"
        >
          +
        </button>
        <button
          title="Zoom out"
          type="button"
          @click="zoomGraph(0.82)"
        >
          -
        </button>
        <button
          title="Fit graph"
          type="button"
          @click="fitGraph"
        >
          Fit
        </button>
        <button
          title="Rerun layout"
          type="button"
          @click="runLayout"
        >
          Layout
        </button>
      </div>
    </div>

    <div
      ref="container"
      class="graph-canvas"
    />
  </div>
</template>

<style scoped>
.graph-shell {
  min-height: 560px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background:
    linear-gradient(rgba(100, 116, 139, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(100, 116, 139, 0.08) 1px, transparent 1px),
    var(--surface-muted);
  background-size: 24px 24px;
  box-shadow: var(--shadow-sm);
}

.graph-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 48px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  color: var(--text);
  font-size: 14px;
  padding: 8px 10px;
}

.graph-toolbar div {
  display: flex;
  gap: 8px;
}

button {
  min-width: 36px;
  min-height: 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text-h);
  font-size: 13px;
  padding: 6px 10px;
}

button:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.graph-canvas {
  width: 100%;
  height: 512px;
}

@media (prefers-color-scheme: dark) {
  .graph-shell {
    background:
      linear-gradient(rgba(148, 163, 184, 0.12) 1px, transparent 1px),
      linear-gradient(90deg, rgba(148, 163, 184, 0.12) 1px, transparent 1px),
      var(--surface-muted);
  }

  .graph-toolbar {
    background: color-mix(in srgb, var(--surface) 92%, transparent);
    color: var(--text);
  }
}

@media (max-width: 760px) {
  .graph-shell {
    min-height: 460px;
  }

  .graph-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .graph-canvas {
    height: 410px;
  }
}
</style>
