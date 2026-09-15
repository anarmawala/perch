import { defineConfig, minimal2023Preset } from "@vite-pwa/assets-generator/config";

// One source SVG -> favicon (browser tab), apple-touch-icon, and the PWA
// install icons (192/512 + maskable). Keeps every icon consistent.
export default defineConfig({
  headLinkOptions: { preset: "2023" },
  preset: minimal2023Preset,
  images: ["public/logo.svg"],
});
