import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import { AuthProvider } from "@/lib/auth/AuthContext";
import { AppRouter } from "@/app/router";
import { Toaster } from "@/components/ui/sonner";
import "@/styles/globals.css";

const USING_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

async function bootstrap() {
  if (USING_MOCKS) {
    const { startMockWorker } = await import("@/mocks/browser");
    await startMockWorker();
  }

  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AppRouter />
          <Toaster />
        </AuthProvider>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}

void bootstrap();
