import { resolve } from "path";
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    lib: {
      entry: resolve(__dirname, "src/index.ts"),
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
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      include: ["src/**/*.ts"],
    },
  },
});
