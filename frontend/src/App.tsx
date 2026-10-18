import { useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type HealthStatus =
  | { state: "checking" }
  | { state: "ok" }
  | { state: "degraded" }
  | { state: "unavailable" };

const STATUS_TEXT: Record<HealthStatus["state"], { title: string; detail: string }> = {
  checking: {
    title: "Verificando conexão com a API…",
    detail: "Aguarde um instante.",
  },
  ok: {
    title: "API conectada — banco de dados OK",
    detail: "O backend e o PostgreSQL estão funcionando.",
  },
  degraded: {
    title: "API respondeu, mas o banco de dados está com erro",
    detail: "Verifique se o PostgreSQL está em execução.",
  },
  unavailable: {
    title: "API indisponível",
    detail: "Verifique se o backend está em execução na porta 8000.",
  },
};

export default function App() {
  const [status, setStatus] = useState<HealthStatus>({ state: "checking" });

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);

    async function checkHealth() {
      try {
        const response = await fetch(`${API_URL}/health`, {
          signal: controller.signal,
        });
        const body = (await response.json()) as { database?: string };
        if (response.ok && body.database === "ok") {
          setStatus({ state: "ok" });
        } else {
          setStatus({ state: "degraded" });
        }
      } catch {
        setStatus({ state: "unavailable" });
      } finally {
        window.clearTimeout(timeout);
      }
    }

    void checkHealth();
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, []);

  const text = STATUS_TEXT[status.state];

  return (
    <main className="flex min-h-dvh items-center justify-center bg-rose-50 p-4">
      <section className="w-full max-w-md rounded-2xl border border-rose-100 bg-white p-6 shadow-sm">
        <h1 className="text-lg font-semibold text-rose-900">Nail Studio Manager</h1>
        <p className="mt-1 text-sm text-stone-500">Fundação técnica (E0)</p>
        <div className="mt-6 flex items-start gap-3" role="status" aria-live="polite">
          <span
            className={`mt-0.5 h-3 w-3 shrink-0 rounded-full ${
              status.state === "ok"
                ? "bg-emerald-500"
                : status.state === "checking"
                  ? "bg-amber-400"
                  : "bg-red-500"
            }`}
          />
          <div>
            <p className="font-medium text-stone-800">{text.title}</p>
            <p className="mt-1 text-sm text-stone-500">{text.detail}</p>
          </div>
        </div>
      </section>
    </main>
  );
}
