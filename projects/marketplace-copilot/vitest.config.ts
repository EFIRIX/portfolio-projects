import { defineConfig } from "vitest/config";
import { resolve } from "node:path";

/**
 * Vitest-конфиг.
 *
 * Тесты используют path-alias @/ (как и остальной код) — маппим его сюда,
 * чтобы vitest (через Vite) находил модули без ts-node.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": resolve(__dirname),
    },
  },
  test: {
    environment: "node",
    include: ["**/*.test.ts"],
  },
});
