import "@/i18n";
import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "@/App";
import { AuthProvider } from "@/auth/AuthContext";
import zhTW from "@/i18n/locales/zh-TW.json";
import { formatBytes, formatContext } from "@/lib/format";

function renderAt(path: string) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <AuthProvider>
            <App />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

describe("App", () => {
  beforeEach(() => sessionStorage.clear());

  it("redirects unauthenticated users to login", () => {
    renderAt("/dashboard");
    expect(screen.getByText(zhTW.login.title)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: zhTW.login.submit })).toBeDisabled();
  });
});

describe("format", () => {
  it("formats bytes and context", () => {
    expect(formatBytes(988097824)).toBe("942.3 MB");
    expect(formatBytes(null)).toBe("—");
    expect(formatContext(32768)).toBe("32K");
    expect(formatContext(null)).toBe("—");
  });
});

describe("i18n", () => {
  it("has every instance status translated", () => {
    for (const s of ["CREATED", "STARTING", "LOADING", "READY", "STOPPING", "STOPPED", "ERROR"]) {
      expect(zhTW.status[s as keyof typeof zhTW.status]).toBeTruthy();
    }
  });
});
