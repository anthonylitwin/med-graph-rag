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
