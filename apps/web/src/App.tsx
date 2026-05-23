import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { ChatPage } from "./routes/ChatPage";
import { GraphPage } from "./routes/GraphPage";

function App() {
  return (
    <BrowserRouter>
      <nav style={{ padding: "1rem", borderBottom: "1px solid #ddd" }}>
        <Link to="/" style={{ marginRight: "1rem" }}>Chat</Link>
        <Link to="/graph">Graph</Link>
      </nav>

      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/graph" element={<GraphPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;