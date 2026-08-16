/// <reference types="vitest" />
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";

/**
 * Keep the mock layer out of any build that is not explicitly a mock build (C10).
 *
 * The JS is already handled: `import.meta.env.VITE_USE_MOCKS === "true"` folds to
 * a literal `false` at build time, so Rollup drops the dynamic `import()` of the
 * mock worker and the "any password works" login path with it. Verified — the
 * production bundle contains none of it.
 *
 * `public/mockServiceWorker.js` is the gap. Vite copies `public/` VERBATIM, so it
 * shipped into `dist/` and was served at `/mockServiceWorker.js` by the
 * production container. On its own it is inert — nothing registers it once the JS
 * is gone — but it is a request-interception service worker sitting on the origin
 * of an app that holds performance reviews, and "inert because the code that
 * registers it happens to be absent" is a property one refactor can undo.
 *
 * So the protection is structural: unless the build is a mock build, the worker is
 * deleted from the output. `closeBundle` rather than `generateBundle` because
 * public/ assets are copied outside the bundle graph.
 */
function stripMockWorkerFromBuild(useMocks: boolean): Plugin {
  return {
    name: "pms-strip-mock-worker",
    apply: "build",
    closeBundle() {
      if (useMocks) return;
      const target = path.resolve(__dirname, "dist/mockServiceWorker.js");
      if (fs.existsSync(target)) {
        fs.unlinkSync(target);
        this.warn("removed mockServiceWorker.js from the production build");
      }
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Read the flag the same way the app does, so there is one answer to "is this a
  // mock build?" rather than two that can disagree.
  const useMocks =
    (process.env.VITE_USE_MOCKS ??
      (mode === "test" ? "false" : "false")) === "true";

  return {
  plugins: [react(), stripMockWorkerFromBuild(useMocks)],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@shared": path.resolve(__dirname, "../shared/src"),
      // shared/ lives outside the frontend root, so its bare `axios` import must
      // be pinned to the frontend's copy (one instance; web only — mobile/Metro
      // resolves shared's deps from mobile/node_modules).
      axios: path.resolve(__dirname, "./node_modules/axios"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
  server: {
    // Allow the dev server to read the sibling shared/ source (outside frontend root).
    fs: { allow: [".."] },
    port: 5173,
    host: true,
  },
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks: {
          "react-vendor": ["react", "react-dom", "react-router-dom"],
          "data-vendor": ["@tanstack/react-query", "@tanstack/react-table", "axios"],
          "chart-vendor": ["recharts"],
          "ui-vendor": [
            "@radix-ui/react-dialog",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-select",
            "@radix-ui/react-tabs",
            "@radix-ui/react-tooltip",
            "lucide-react",
          ],
        },
      },
    },
  },
  };
});
