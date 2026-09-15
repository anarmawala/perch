import { defineConfig } from "vite";
import preact from "@preact/preset-vite";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import { fileURLToPath } from "node:url";

// The web app talks to the API through /api/* — proxied here in dev, reverse-proxied
// by nginx in prod. Keeps everything same-origin (no CORS). VITE_API_PROXY lets the
// dev container point at the `api` service instead of localhost.
export default defineConfig({
  plugins: [
    preact(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      pwaAssets: { config: true },
      manifest: {
        name: "Perch",
        short_name: "Perch",
        description: "Backyard wildlife camera — watch, identify, and get notified about visiting birds.",
        theme_color: "#f6f7f9",
        background_color: "#f6f7f9",
        display: "standalone",
        start_url: "/",
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
        navigateFallbackDenylist: [/^\/api/], // never serve the app shell for API routes
      },
    }),
  ],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    host: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
