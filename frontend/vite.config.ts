import { realpathSync } from "fs";
import { resolve } from "path";
import { fileURLToPath } from "url";
import { defineConfig, normalizePath } from "vite";

// Canonical cross-platform project root (normalizes Windows drive letter & slashes)
const projectRoot = normalizePath(realpathSync.native(fileURLToPath(new URL(".", import.meta.url))));

export default defineConfig({
  root: projectRoot,
  build: {
    lib: {
      entry: resolve(projectRoot, "src/index.ts"),
      name: "JakeAIWidget",
      fileName: (format) => `jake-ai-widget.${format}.js`,
      formats: ["es", "umd"],
    },
    rollupOptions: {
      output: {
        assetFileNames: "style.[ext]",
        exports: "named",
      },
    },
    sourcemap: true,
    emptyOutDir: true,
  },
  test: {
    environment: "happy-dom",
    globals: true,
    include: ["tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      include: ["src/**/*.ts"],
      exclude: ["src/playground.ts", "src/vite-env.d.ts"],
    },
  },
});
