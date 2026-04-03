import { readdirSync } from "fs";
import { join } from "path";

const isWatch = process.argv.includes("--watch");

// Collect all TypeScript entry points from src/
const entryPoints = [];
try {
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith(".ts")) entryPoints.push(full);
    }
  };
  walk("src");
} catch {
  // src/ may not contain any .ts files yet
}

if (entryPoints.length === 0) {
  console.log("esbuild: no TypeScript entry points found — skipping.");
  process.exit(0);
}

// Only import esbuild when we actually have files to build
const esbuild = await import("esbuild");

const ctx = await esbuild.context({
  entryPoints,
  bundle: true,
  outdir: "dist/js",
  format: "esm",
  sourcemap: true,
  target: "es2020",
});

if (isWatch) {
  await ctx.watch();
  console.log("esbuild: watching for changes…");
} else {
  await ctx.rebuild();
  await ctx.dispose();
  console.log(`esbuild: built ${entryPoints.length} entry point(s).`);
}
