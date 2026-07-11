export default function HomePage() {
  return (
    <main style={{ padding: "2rem", fontFamily: "system-ui, sans-serif" }}>
      <h1>RAG Lab Baseline</h1>
      <p>Docker stack is running. Backend health: <code>/health</code></p>
      <p>
        <a href="/experiment" style={{ color: "#00f0ff" }}>
          Open Lab Notebook →
        </a>
      </p>
      <p>
        <a href="/rag" style={{ color: "#ff00aa" }}>
          Open RAG Console →
        </a>
      </p>
    </main>
  );
}
