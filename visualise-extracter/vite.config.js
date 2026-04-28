import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages project-site base path: /<repo-name>/<subpath>/
// Repo: Vitark42/demo-repository → site root /demo-repository/
// This sub-app lives under /visualise-extracter/ within that.
export default defineConfig({
  plugins: [react()],
  base: "/demo-repository/visualise-extracter/",
  build: {
    outDir: "dist",
  },
});
