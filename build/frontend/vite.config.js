import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev/Docker, proxy /api and /ws straight to the FastAPI backend so the
// browser only ever talks to one origin (localhost:5173). Override with
// VITE_BACKEND_URL for Docker (see docker-compose.yml) or a remote backend.
const backendTarget = process.env.VITE_BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: backendTarget, changeOrigin: true },
      "/ws": { target: backendTarget, ws: true, changeOrigin: true },
    },
  },
  preview: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: backendTarget, changeOrigin: true },
      "/ws": { target: backendTarget, ws: true, changeOrigin: true },
    },
  },
});
