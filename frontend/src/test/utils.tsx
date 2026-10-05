import "@/i18n";
import { MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthContext";

export type Handler = (url: string, init?: RequestInit) => unknown;

export function mockFetch(routes: Record<string, Handler>) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    const key = Object.keys(routes).find((k) => {
      const [m, p] = k.split(" ");
      return m === method && url.replace(/^\/api\/v1/, "").split("?")[0] === p;
    });
    if (!key) return new Response(JSON.stringify({ detail: { code: "NOT_MOCKED" } }), { status: 404 });
    const data = routes[key]!(url, init);
    return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

export function renderRoute(element: ReactElement, path: string, pattern: string) {
  sessionStorage.setItem("dgxsp.token", "t");
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <ModalsProvider>
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <AuthProvider>
              <Routes>
                <Route path={pattern} element={element} />
                <Route path="*" element={<div data-testid="navigated" />} />
              </Routes>
            </AuthProvider>
          </MemoryRouter>
        </QueryClientProvider>
      </ModalsProvider>
    </MantineProvider>,
  );
}
