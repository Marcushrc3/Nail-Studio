import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function mockFetchOnce(implementation: () => Promise<Response>) {
  const fetchMock = vi.fn(implementation);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App (estado da API)", () => {
  it("mostra status ok quando o banco responde", async () => {
    mockFetchOnce(async () =>
      new Response(JSON.stringify({ status: "ok", database: "ok" }), { status: 200 }),
    );
    render(<App />);
    expect(await screen.findByText(/banco de dados OK/)).toBeInTheDocument();
  });

  it("mostra erro quando o banco está indisponível", async () => {
    mockFetchOnce(async () =>
      new Response(JSON.stringify({ status: "degraded", database: "error" }), {
        status: 503,
      }),
    );
    render(<App />);
    expect(
      await screen.findByText(/banco de dados está com erro/),
    ).toBeInTheDocument();
  });

  it("mostra indisponível quando a API não responde", async () => {
    mockFetchOnce(async () => {
      throw new Error("conexão recusada");
    });
    render(<App />);
    expect(await screen.findByText(/API indisponível/)).toBeInTheDocument();
  });
});
