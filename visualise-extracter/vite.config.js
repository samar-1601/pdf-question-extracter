import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages project-site base path: /<repo-name>/
// Repo: samar-1601/pdf-question-extracter → deployed at /pdf-question-extracter/
// The workflow uploads only this app's dist folder, so the visualiser is the
// site root (not nested under /visualise-extracter/).
export default defineConfig({
  plugins: [react()],
  base: "/pdf-question-extracter/",
  build: {
    outDir: "dist",
  },
});
