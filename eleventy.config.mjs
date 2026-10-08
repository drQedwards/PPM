import { createRequire } from "node:module";
import path from "node:path";

function loadMarkdownIt() {
  const require = createRequire(import.meta.url);
  const candidates = [
    "markdown-it",
    "@11ty/eleventy/node_modules/markdown-it",
  ];
  for (const id of candidates) {
    try {
      return require(id);
    } catch {
      // try the next location
    }
  }
  throw new Error("markdown-it was not found. It ships with @11ty/eleventy.");
}

function pagesPrefix() {
  const raw = process.env.PATH_PREFIX;
  if (raw) {
    if (raw === "/") return "/";
    let prefix = raw.startsWith("/") ? raw : `/${raw}`;
    if (!prefix.endsWith("/")) prefix += "/";
    return prefix;
  }
  // GITHUB_REPOSITORY keeps the repo's case (drQedwards/PPM), so compare
  // case-insensitively; GitHub Pages serves the site under /PPM/ and /pmll/.
  const repo = (process.env.GITHUB_REPOSITORY || "").toLowerCase();
  if (repo.endsWith("/ppm")) return "/PPM/";
  if (repo.endsWith("/pmll")) return "/pmll/";
  return "/";
}

/*
 * Doc pages are rendered at /docs/<slug>/, not at their source path, so a
 * relative link such as `STELLAR.md` inside docs/SCF.md must be resolved
 * against the source file. Links to another rendered doc go to its page;
 * other relative repository files go to GitHub. Absolute URLs, root-relative
 * paths and in-page anchors are left alone.
 */
function resolveDocHref(href, env, prefix, repo) {
  if (!href || !env || !env.source) return null;
  if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("#") || href.startsWith("/")) return null;
  const hashAt = href.indexOf("#");
  const target = hashAt === -1 ? href : href.slice(0, hashAt);
  const hash = hashAt === -1 ? "" : href.slice(hashAt);
  if (!target) return null;
  const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(env.source), target));
  if (resolved.startsWith("../")) return null;
  const page = (env.pages || []).find((p) => p.source === resolved);
  if (page) return `${prefix}docs/${page.slug}/${hash}`;
  if (repo) return `https://github.com/${repo}/blob/main/${resolved}${hash}`;
  return null;
}

export default function (eleventyConfig) {
  const markdownIt = loadMarkdownIt();
  const md = markdownIt({
    html: true,
    linkify: true,
    typographer: false,
  });

  eleventyConfig.addPassthroughCopy({ "src/assets": "assets" });
  const prefix = pagesPrefix();
  const repo = process.env.DOCS_REPO || process.env.GITHUB_REPOSITORY || "";
  const defaultLinkOpen =
    md.renderer.rules.link_open ||
    ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const fixed = resolveDocHref(tokens[idx].attrGet("href"), env, prefix, repo);
    if (fixed) tokens[idx].attrSet("href", fixed);
    return defaultLinkOpen(tokens, idx, options, env, self);
  };

  // renderMarkdown(doc, docPages): pass the doc so relative links resolve.
  eleventyConfig.addFilter("renderMarkdown", (value, doc, pages) =>
    md.render(String(value || ""), doc ? { source: doc.source, pages: pages || [] } : {}),
  );
  eleventyConfig.addFilter("inc", (n) => Number(n) + 1);
  eleventyConfig.addFilter("dec", (n) => Number(n) - 1);
  eleventyConfig.addFilter("at", (arr, index) => {
    if (!Array.isArray(arr)) return undefined;
    return arr[Number(index)];
  });

  return {
    pathPrefix: prefix,
    dir: {
      input: "src",
      output: "dist",
      includes: "_includes",
    },
    htmlTemplateEngine: "liquid",
    markdownTemplateEngine: "liquid",
  };
};
