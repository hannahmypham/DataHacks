import { health, submitScan } from "./lib/api";
import { useEffect, useState, useRef } from "react";

type ScanResponse = {
  scan_id: string;
  s3_url: string;
  food_items: any[];
  plastic_items: any[];
  totals: Record<string, unknown>;
};

export default function App() {
  const [status, setStatus] = useState<string>("…");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    health()
      .then((r) => setStatus(r.status || "ok"))
      .catch((e) => setStatus(`err: ${e.message}`));
  }, []);

  const handleFileSelect = async (file: File) => {
    if (!file) return;

    setIsAnalyzing(true);
    setError("");
    setResult(null);

    try {
      // Test values - in real app these would come from auth/user selection
      const response = await submitScan(
        file,
        "test-restaurant-001",
        "92101",
        "Downtown"
      );

      setResult(response);
      console.log("✅ Scan complete:", response);
    } catch (err: any) {
      setError(err.message || "Failed to analyze image");
      console.error(err);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) {
      handleFileSelect(file);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  return (
    <main className="min-h-screen bg-zinc-950 text-white p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 bg-emerald-500 rounded-xl flex items-center justify-center text-2xl">
            ♻️
          </div>
          <div>
            <h1 className="text-5xl font-bold tracking-tight">SnapTrash</h1>
            <p className="text-zinc-400">Waste Intelligence Pipeline Test</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-6">
          {/* Upload Panel */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-8">
            <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
              📸 Test Image Upload
            </h2>

            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-2xl p-12 text-center transition-all cursor-pointer
                ${isAnalyzing
                  ? "border-emerald-500 bg-emerald-950/30"
                  : "border-zinc-700 hover:border-zinc-500 hover:bg-zinc-900"
                }`}
            >
              <div className="mx-auto w-16 h-16 bg-zinc-800 rounded-2xl flex items-center justify-center mb-4">
                📷
              </div>
              <p className="text-lg font-medium mb-1">
                {isAnalyzing ? "Analyzing waste bin..." : "Drop waste bin photo here"}
              </p>
              <p className="text-sm text-zinc-500 mb-6">
                or click to upload • Supports JPG, PNG
              </p>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
              />

              <div className="text-xs text-zinc-500">
                Backend will: upload to S3 → call Grok (xAI) Vision → enrich → write to Databricks
              </div>
            </div>

            {error && (
              <div className="mt-4 p-4 bg-red-950 border border-red-900 rounded-2xl text-red-400 text-sm">
                {error}
              </div>
            )}
          </div>

          {/* Results Panel */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-8">
            <h2 className="text-xl font-semibold mb-6">Analysis Results</h2>

            {result ? (
              <div className="space-y-6">
                <div className="bg-zinc-950 border border-zinc-800 rounded-2xl p-5">
                  <div className="text-emerald-400 text-sm font-mono mb-2">SCAN ID</div>
                  <div className="font-mono text-xs break-all text-zinc-400">{result.scan_id}</div>
                </div>

                <div>
                  <div className="text-sm text-zinc-400 mb-3">FOOD ITEMS DETECTED</div>
                  <div className="space-y-3">
                    {result.food_items.map((item, i) => (
                      <div key={i} className="bg-zinc-950 border border-zinc-800 rounded-2xl p-4 text-sm">
                        <div className="flex justify-between">
                          <span className="font-medium">{item.type}</span>
                          <span className="text-emerald-400">{item.estimated_kg}kg</span>
                        </div>
                        <div className="text-xs text-zinc-500 mt-1">
                          Decay: {item.decay_stage}/5 • {item.contaminated ? "❌ Contaminated" : "✅ Clean"}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="text-sm text-zinc-400 mb-3">PLASTIC / PACKAGING</div>
                  <div className="space-y-3">
                    {result.plastic_items.map((item, i) => (
                      <div key={i} className="bg-zinc-950 border border-zinc-800 rounded-2xl p-4 text-sm">
                        <div className="font-medium">{item.type}</div>
                        {item.resin_code && <div className="text-xs text-amber-400">Resin #{item.resin_code}</div>}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-4 border-t border-zinc-800">
                  <a
                    href={result.s3_url}
                    target="_blank"
                    className="text-xs text-blue-400 hover:text-blue-300 underline"
                  >
                    View uploaded image in S3 →
                  </a>
                </div>
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-zinc-500 text-sm">
                Upload an image on the left to test the full pipeline
              </div>
            )}
          </div>
        </div>

        <div className="mt-8 text-center text-xs text-zinc-600">
          Backend: http://localhost:8000 • Frontend: http://localhost:5173<br />
          Data flows: Image → S3 → Grok (xAI) Vision → Analysis → Databricks Delta Lake
        </div>
      </div>
    </main>
  );
}
