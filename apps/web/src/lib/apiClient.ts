export type ChatRequest = {
    message: string;
    modelProfile?: string;
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

export type ModelOption = {
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

export type ModelOptionsResponse = {
    defaultProfile: string;
    profiles: ModelOption[];
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

export async function getChatModelOptions(): Promise<ModelOptionsResponse> {
    const response = await fetch(`${API_BASE_URL}/chat/model-options`);

    if (!response.ok) {
        throw new Error(`Model options request failed: ${response.status}`);
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
};

export async function getSampleGraph(): Promise<GraphResponse> {
  const response = await fetch(`${API_BASE_URL}/graph/sample`);

  if (!response.ok) {
    throw new Error(`Graph request failed: ${response.status}`);
  }

  return response.json();
}
