import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/graphql": "http://localhost:8000",
      "/chat": "http://localhost:8000",
      "/admin": "http://localhost:8000",
      "/healthz": "http://localhost:8000",
    },
  },
});
