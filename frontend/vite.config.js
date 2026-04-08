// frontend/vite.config.js
//
// Vite configuration for the FreeMAD React frontend.
//
// The key setting here is the dev server proxy:
//   During local development, the React dev server runs on port 5173
//   and Django runs on port 8000. Without the proxy, a fetch to
//   '/api/chat/' from the browser would go to port 5173 (wrong).
//   The proxy transparently forwards /api/* to localhost:8000 so
//   CORS is bypassed and the URL stays clean in your code.
//
// In production (Docker / Render) there is only one server — Django
// on port 8000 — so the proxy is irrelevant.

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],

  server: {
    port: 5173,

    proxy: {
      // Forward /api/* requests to the Django backend during development.
      // Change the target port if Django is running on a different port.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,   // rewrites the Host header to match the target
        secure: false,        // allow self-signed certs if testing with HTTPS locally
      },
    },
  },

  build: {
    // Output directory — the Dockerfile copies this to backend/frontend_build/
    outDir: "dist",
    emptyOutDir: true,
  },
});
