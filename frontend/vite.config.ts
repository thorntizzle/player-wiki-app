import react from "@vitejs/plugin-react";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
    }),
    react(),
  ],
  base: "/app-next/",
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: false,
      },
      "/campaigns": {
        target: "http://127.0.0.1:5000",
        changeOrigin: false,
      },
      "/typescript-api": {
        target: "http://127.0.0.1:3000",
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/typescript-api/, ""),
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
