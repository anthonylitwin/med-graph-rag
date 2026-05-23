import { useEffect, useState } from "react";
import { getSampleGraph, type GraphResponse } from "../lib/apiClient";

export function GraphPage() {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadGraph() {
    try {
      setError(null);
      const result = await getSampleGraph();
      setGraph(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }

  useEffect(() => {
    loadGraph();
  }, []);

  return (
    <main style={{ maxWidth: 1000, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <h1>Sample Biomedical Graph</h1>

      <button onClick={loadGraph}>Refresh Graph</button>

      {error && (
        <p style={{ color: "red" }}>
          Error: {error}
        </p>
      )}

      {graph && (
        <>
          <section style={{ marginTop: "2rem" }}>
            <h2>Nodes</h2>
            <ul>
              {graph.nodes.map((node) => (
                <li key={node.id}>
                  <strong>{node.labels.join(", ")}</strong>:{" "}
                  {String(node.properties.name ?? node.properties.title ?? node.id)}
                </li>
              ))}
            </ul>
          </section>

          <section style={{ marginTop: "2rem" }}>
            <h2>Relationships</h2>
            <ul>
              {graph.relationships.map((relationship, index) => (
                <li key={`${relationship.source}-${relationship.type}-${relationship.target}-${index}`}>
                  {relationship.source} -- <strong>{relationship.type}</strong> --&gt;{" "}
                  {relationship.target}
                </li>
              ))}
            </ul>
          </section>

          <section style={{ marginTop: "2rem" }}>
            <h2>Raw Graph JSON</h2>
            <pre style={{ background: "#f5f5f5", padding: "1rem", overflow: "auto" }}>
              {JSON.stringify(graph, null, 2)}
            </pre>
          </section>
        </>
      )}
    </main>
  );
}