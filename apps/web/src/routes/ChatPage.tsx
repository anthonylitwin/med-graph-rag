import { useEffect, useState } from "react";
import {
  getChatModelOptions,
  sendChatMessage,
  type ChatResponse,
  type ModelOption,
} from "../lib/apiClient";

const FALLBACK_MODEL_OPTIONS: ModelOption[] = [
  {
    name: "frontier",
    label: "Frontier API",
    description: "Configured OpenAI frontier runtime.",
    qa_provider: "openai",
    qa_model: "gpt-5.5",
    qa_retriever: "graph",
    extractor_provider: "openai",
    extractor_model: "gpt-5.5",
    entity_model: "",
  },
  {
    name: "local-qwen25",
    label: "Local Qwen 2.5",
    description: "Ollama qwen2.5:7b-instruct runtime.",
    qa_provider: "ollama",
    qa_model: "qwen2.5:7b-instruct",
    qa_retriever: "graph",
    extractor_provider: "gliner_ollama",
    extractor_model: "qwen2.5:7b-instruct",
    entity_model: "Ihor/gliner-biomed-small-v1.0",
  },
  {
    name: "local-qwen3",
    label: "Local Qwen 3",
    description: "Ollama qwen3:8b runtime.",
    qa_provider: "ollama",
    qa_model: "qwen3:8b",
    qa_retriever: "graph",
    extractor_provider: "gliner_ollama",
    extractor_model: "qwen3:8b",
    entity_model: "Ihor/gliner-biomed-small-v1.0",
  },
  {
    name: "noop",
    label: "Noop",
    description: "Deterministic smoke-test runtime.",
    qa_provider: "noop",
    qa_model: "noop-language-model-v0",
    qa_retriever: "noop",
    extractor_provider: "noop",
    extractor_model: "noop-extractor-v0",
    entity_model: "",
  },
];

export function ChatPage() {
  const [message, setMessage] = useState("");
  const [modelProfile, setModelProfile] = useState("frontier");
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(FALLBACK_MODEL_OPTIONS);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let isMounted = true;

    getChatModelOptions()
      .then((options) => {
        if (!isMounted) {
          return;
        }
        setModelOptions(options.profiles);
        setModelProfile(options.defaultProfile);
      })
      .catch(() => {
        setModelOptions(FALLBACK_MODEL_OPTIONS);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    if (!message.trim()) {
      return;
    }

    setIsLoading(true);
    setResponse(null);

    try {
      const result = await sendChatMessage({ message, modelProfile });
      setResponse(result);
    } catch (error) {
      setResponse({
        answer: `Error: ${error instanceof Error ? error.message : "Unknown error"}`,
        sources: [],
        reasoningPath: [],
        model: "error",
        provider: "error",
        modelProfile,
      });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 900, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <h1>MedGraphRAG</h1>
      <p>Ask a biomedical question against the configured graph evidence.</p>

      <form onSubmit={handleSubmit}>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginBottom: "1rem" }}>
          <label htmlFor="model-profile">Model</label>
          <select
            id="model-profile"
            value={modelProfile}
            onChange={(event) => setModelProfile(event.target.value)}
            style={{ minWidth: 220, padding: "0.5rem" }}
          >
            {modelOptions.map((option) => (
              <option key={option.name} value={option.name}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

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
          <p>
            {response.model} ({response.provider}, {response.modelProfile})
          </p>

          {typeof response.confidence === "number" && (
            <>
              <h3>Confidence</h3>
              <p>{Math.round(response.confidence * 100)}%</p>
            </>
          )}

          {response.abstained && (
            <p>
              The answerer abstained because the retrieved graph evidence was
              insufficient.
            </p>
          )}

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
