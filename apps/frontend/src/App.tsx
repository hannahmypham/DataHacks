import { health } from "./lib/api";
import { useEffect, useState } from "react";

export default function App() {
  const [status, setStatus] = useState<string>("…");
  useEffect(() => {
    health().then((r) => setStatus(r.status)).catch((e) => setStatus(`err: ${e.message}`));
  }, []);

  return (
    <main className="min-h-screen p-8 max-w-4xl mx-auto">
      <h1 className="text-4xl font-bold text-brand">SnapTrash</h1>
      <p className="mt-2 text-zinc-400">Restaurant waste vision + analytics dashboard.</p>

      <section className="mt-8 rounded-xl border border-zinc-800 p-6">
        <h2 className="text-lg font-semibold">Backend health</h2>
        <p className="font-mono text-sm mt-2">/health → {status}</p>
      </section>

      <section className="mt-4 text-sm text-zinc-500">
        Drop dashboards here via Lovable / shadcn-ui MCP / 21st.dev components.
      </section>
    </main>
  );
}
