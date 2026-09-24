import vinext from "vinext";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vinext()],
  server: {
    host: "0.0.0.0",
    ...(process.env.CODEX_SANDBOX === "seatbelt"
      ? { watch: { useFsEvents: false, usePolling: true } }
      : {}),
    proxy: {
      "/api": {
        // Keep the proxy configurable so this app can coexist with another
        // local service that already occupies port 8000.
        target: process.env.BACKEND_PROXY_TARGET || "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
});
