import fs from "node:fs";
import path from "node:path";

const ORDERED = [
  ["docs/codedocs/index.md", "Core"],
  ["docs/codedocs/architecture.md", "Core"],
  ["docs/codedocs/mcp-tools.md", "Core"],
  ["docs/codedocs/kv-silo.md", "Core"],
  ["docs/codedocs/q-promises.md", "Core"],
  ["docs/codedocs/semantic-memory-graph.md", "Core"],
  ["docs/codedocs/solution-engine.md", "Core"],
  ["docs/codedocs/types.md", "Core"],
  ["docs/codedocs/guides/install-and-run.md", "Guides"],
  ["docs/codedocs/guides/cache-patterns.md", "Guides"],
  ["docs/codedocs/guides/semantic-memory-workflows.md", "Guides"],
  ["docs/codedocs/api-reference/server-tools.md", "API"],
  ["docs/codedocs/api-reference/pmmemorystore.md", "API"],
  ["docs/codedocs/api-reference/qpromiseregistry.md", "API"],
  ["docs/codedocs/api-reference/memory-graph.md", "API"],
  ["docs/codedocs/api-reference/embeddings.md", "API"],
  ["docs/codedocs/api-reference/solution-engine.md", "API"],
  ["docs/SCF.md", "Notes"],
  ["docs/STELLAR.md", "Notes"],
  ["SKILL.md", "Notes"],
  ["docs/NFT.md", "Notes"],
  ["docs/SCF-DISCORD.md", "Notes"],
];

function stripFrontMatter(raw) {
  if (!raw.startsWith("---")) return { meta: {}, body: raw };
  const end = raw.indexOf("\n---", 3);
  if (end === -1) return { meta: {}, body: raw };
  const fm = raw.slice(4, end);
  const body = raw.slice(end + 4).replace(/^\r?\n/, "");
  const meta = {};
  for (const line of fm.split(/\r?\n/)) {
    const match = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (!match) continue;
    meta[match[1]] = match[2].trim().replace(/^["']|["']$/g, "");
  }
  return { meta, body };
}

function titleFrom(meta, body, rel) {
  if (meta.title) return meta.title;
  const heading = body.match(/^#\s+(.+)$/m);
  if (heading) return heading[1].trim();
  return path.basename(rel, path.extname(rel));
}

function slugFrom(rel) {
  let slug = rel.replace(/\.(md|mdx)$/i, "");
  if (slug.startsWith("docs/")) slug = slug.slice("docs/".length);
  return slug.replace(/[^a-zA-Z0-9/_-]+/g, "-").replace(/\/+/g, "/").toLowerCase();
}

function pageFrom(root, rel, section) {
  const abs = path.join(root, rel);
  if (!fs.existsSync(abs)) return null;
  const raw = fs.readFileSync(abs, "utf8");
  const { meta, body } = stripFrontMatter(raw);
  const title = titleFrom(meta, body, rel);
  let markdown = body.replace(/^\uFEFF/, "");
  const firstHeading = markdown.match(/^#\s+(.+)\r?\n+/);
  if (firstHeading && firstHeading[1].trim() === title) {
    markdown = markdown.slice(firstHeading[0].length);
  }
  return {
    title,
    description: meta.description || "",
    section,
    slug: slugFrom(rel),
    source: rel,
    markdown,
  };
}

export default function () {
  const root = process.cwd();
  const pages = [];
  for (const [rel, section] of ORDERED) {
    const page = pageFrom(root, rel, section);
    if (page) pages.push(page);
  }
  if (pages.length === 0) {
    throw new Error("docPages: no documentation markdown found under docs/ or SKILL.md");
  }
  pages.forEach((page, index) => {
    page.n = index + 1;
    page.total = pages.length;
  });
  return pages;
};
