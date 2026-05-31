import { useState } from "react";
import { sendChatMessage, type ChatResponse } from "../lib/apiClient";

export function ChatPage() {
  const [message, setMessage] = useState("");
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    if (!message.trim()) {
      return;
    }

    setIsLoading(true);
    setResponse(null);

    try {
      const result = await sendChatMessage({ message });
      setResponse(result);
    } catch (error) {
      setResponse({
        answer: `Error: ${error instanceof Error ? error.message : "Unknown error"}`,
        sources: [],
        reasoningPath: [],
        model: "error",
      });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 900, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <h1>MedGraphRAG</h1>
      <p>Ask a biomedical question. For now, this calls the mock FastAPI backend.</p>

      <form onSubmit={handleSubmit}>
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          rows={5}
          style={{ width: "100%", padding: "1rem" }}
          placeholder="Ask a question..."
        />

        <button type="submit" disabled={isLoading} style={{ marginTop: "1rem" }}>
          {isLoading ? "Asking..." : "Ask"}
        </button>
      </form>

      {response && (
        <section style={{ marginTop: "2rem" }}>
          <h2>Answer</h2>
          <p>{response.answer}</p>

          <h3>Model</h3>
          <p>{response.model}</p>

          <h3>Sources</h3>
          {response.sources.length === 0 ? (
            <p>No sources returned.</p>
          ) : (
            <ul>
              {response.sources.map((source, index) => (
                <li key={index}>
                  <strong>{String(source.title ?? "Untitled source")}</strong>
                  <br />
                  <span>{String(source.evidenceText ?? "No evidence text")}</span>
                </li>
              ))}
            </ul>
          )}

          <h3>Reasoning Path</h3>
          {response.reasoningPath.length === 0 ? (
            <p>No reasoning path returned.</p>
          ) : (
            <ul>
              {response.reasoningPath.map((step, index) => (
                <li key={index}>
                  {String(step.source)} --{" "}
                  <strong>{String(step.relationship)}</strong>
                  {" --> "}
                  {String(step.target)}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}