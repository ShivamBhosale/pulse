import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { registerSW } from "virtual:pwa-register";
import { Locked } from "./api/client";
import { AppShell } from "./components/AppShell";
import { PasscodeGate } from "./components/PasscodeGate";
import "./index.css";
import { ThemeProvider } from "./lib/theme";
import { SleepPage } from "./pages/Sleep";
import { TodayPage } from "./pages/Today";

registerSW({ immediate: true });

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: true,
      retry: (count, err) => !(err instanceof Locked) && count < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <PasscodeGate>
          <BrowserRouter>
            <AppShell>
              <Routes>
                <Route path="/" element={<TodayPage />} />
                <Route path="/sleep" element={<SleepPage />} />
                <Route path="*" element={<TodayPage />} />
              </Routes>
            </AppShell>
          </BrowserRouter>
        </PasscodeGate>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
