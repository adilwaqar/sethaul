import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Proxy target is switchable:
//   npm run dev                  -> local FastAPI server (http://localhost:8000)
//   npm run dev -- --mode remote -> deployed server (.env.remote)
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_PROXY_TARGET || "http://localhost:8000";

  return {
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        "/api": {
          target,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
