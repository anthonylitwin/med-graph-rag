export type ChatRequest = {
    message: string;
};

export type ChatResponse = {
    answer: string;
    sources: Array<Record<string, unknown>>;
    reasoningPath: Array<Record<string, unknown>>;
    model: string;
};

const API_BASE_URL = 
    import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080";

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
        throw new Error(`Chat request failed: $(response.status)`);
    }

    return response.json();
}
