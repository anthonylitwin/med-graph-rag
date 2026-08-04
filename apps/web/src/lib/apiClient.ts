export type ChatRequest = {
    message: string;
};

export type ChatResponse = {
    answer: string;
    sources: Array<Record<string, unknown>>;
    reasoningPath: Array<Record<string, unknown>>;
    model: string;
    provider: string;
    modelProfile: string;
    confidence?: number;
    abstained?: boolean;
};

const API_BASE_URL = 
    import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function sendChatMessage(
    request: ChatRequest
): Promise<ChatResponse> {
    const response = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
    });

    if (!response.ok){
        throw new Error(`Chat request failed: ${response.status}`);
    }

    return response.json();
}

export type GraphNode = {
  id: string;
  labels: string[];
  properties: Record<string, unknown>;
};

export type GraphRelationship = {
  source: string;
  target: string;
  type: string;
  properties: Record<string, unknown>;
};

export type GraphResponse = {
  nodes: GraphNode[];
  relationships: GraphRelationship[];
  metadata?: {
    q?: string | null;
    label?: string | null;
    relationshipType?: string | null;
    pmcid?: string | null;
    limit?: number;
    nodeCount?: number;
    relationshipCount?: number;
  };
};

export async function getSampleGraph(): Promise<GraphResponse> {
  const response = await fetch(`${API_BASE_URL}/graph/sample`);

  if (!response.ok) {
    throw new Error(`Graph request failed: ${response.status}`);
  }

  return response.json();
}

export type GraphBrowseParams = {
  q?: string;
  label?: string;
  relationshipType?: string;
  pmcid?: string;
  limit?: number;
};

export async function browseGraph(params: GraphBrowseParams = {}): Promise<GraphResponse> {
  const query = new URLSearchParams();

  if (params.q) {
    query.set("q", params.q);
  }

  if (params.label) {
    query.set("label", params.label);
  }

  if (params.relationshipType) {
    query.set("relationshipType", params.relationshipType);
  }

  if (params.pmcid) {
    query.set("pmcid", params.pmcid);
  }

  if (params.limit) {
    query.set("limit", String(params.limit));
  }

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const response = await fetch(`${API_BASE_URL}/graph/browse${suffix}`);

  if (!response.ok) {
    throw new Error(`Graph browse request failed: ${response.status}`);
  }

  return response.json();
}

export type IngestionDocument = {
  documentKey: string;
  title: string;
  status: string;
  fetchStatus: string;
  extractStatus: string;
  loadStatus: string;
  chunkCount: number;
  entityCount: number;
  relationshipCount: number;
  error: string;
};

export type IngestionJob = {
  id: string;
  sourceType: 'pmc' | 'text';
  status: string;
  submittedAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  progressCurrent: number;
  progressTotal: number;
  modelProfile: string;
  applySchema: boolean;
  skipLoad: boolean;
  failFast: boolean;
  outputRoot: string;
  error: string;
  documents?: IngestionDocument[];
};

export type IngestionJobRequest = {
  sourceType: 'pmc' | 'text';
  pmcids?: string[];
  pmcidText?: string;
  documents?: Array<{
    title?: string;
    text: string;
    sourceName?: string;
  }>;
  applySchema?: boolean;
  skipLoad?: boolean;
  failFast?: boolean;
};

export type IngestionModelProfile = {
  name: string;
  label: string;
  description: string;
  qa_provider: string;
  qa_model: string;
  qa_retriever: string;
  extractor_provider: string;
  extractor_model: string;
  entity_model: string;
};

export type IngestionArtifacts = {
  jobId: string;
  outputRoot: string;
  files: Array<{
    path: string;
    relativePath: string;
    size: number;
  }>;
};

export async function createIngestionJob(request: IngestionJobRequest): Promise<IngestionJob> {
  const response = await fetch(`${API_BASE_URL}/ingestion/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(
      `Ingestion request failed: ${response.status}${payload?.detail ? ` ${payload.detail}` : ''}`
    );
  }

  return response.json();
}

export async function listIngestionJobs(limit = 50): Promise<IngestionJob[]> {
  const response = await fetch(`${API_BASE_URL}/ingestion/jobs?limit=${limit}`);

  if (!response.ok) {
    throw new Error(`Ingestion queue request failed: ${response.status}`);
  }

  const payload = await response.json();
  return payload.jobs;
}

export async function getIngestionJob(jobId: string): Promise<IngestionJob> {
  const response = await fetch(`${API_BASE_URL}/ingestion/jobs/${encodeURIComponent(jobId)}`);

  if (!response.ok) {
    throw new Error(`Ingestion job request failed: ${response.status}`);
  }

  return response.json();
}

export async function getIngestionArtifacts(jobId: string): Promise<IngestionArtifacts> {
  const response = await fetch(`${API_BASE_URL}/ingestion/jobs/${encodeURIComponent(jobId)}/artifacts`);

  if (!response.ok) {
    throw new Error(`Ingestion artifacts request failed: ${response.status}`);
  }

  return response.json();
}

export async function getIngestionModelOptions(): Promise<IngestionModelProfile> {
  const response = await fetch(`${API_BASE_URL}/ingestion/model-options`);

  if (!response.ok) {
    throw new Error(`Ingestion model options request failed: ${response.status}`);
  }

  const payload = await response.json();
  return payload.activeProfile;
}
