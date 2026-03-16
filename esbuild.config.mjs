/**
 * esbuild.config.mjs — Build script for the PPM website TypeScript assets.
 *
 * Bundles `src/js/main.ts` (and its imports) into `dist/js/bundle.js`.
 *
 * Usage:
 *   node esbuild.config.mjs           # one-shot production build
 *   node esbuild.config.mjs --watch   # incremental dev build
 */

import * as esbuild from "esbuild";
import { argv } from "process";

const watch = argv.includes("--watch");
const isDev = watch || process.env.NODE_ENV === "development";

/** @type {import('esbuild').BuildOptions} */
const config = {
  entryPoints: ["src/js/main.ts"],
  bundle: true,
  outfile: "dist/js/bundle.js",
  format: "esm",
  target: ["es2020"],
  platform: "browser",
  sourcemap: isDev,
  minify: !isDev,
  /* Tree-shake unused d3 submodules */
  treeShaking: true,
  logLevel: "info",
};

if (watch) {
  const ctx = await esbuild.context(config);
  await ctx.watch();
  console.log("esbuild: watching for changes…");
} else {
  await esbuild.build(config);
}
