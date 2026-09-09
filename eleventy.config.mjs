import { createRequire } from "node:module";

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
  const repo = process.env.GITHUB_REPOSITORY || "";
  if (repo.endsWith("/ppm")) return "/PPM/";
  if (repo.endsWith("/pmll")) return "/pmll/";
  return "/";
}

export default function (eleventyConfig) {
  const markdownIt = loadMarkdownIt();
  const md = markdownIt({
    html: true,
    linkify: true,
    typographer: false,
  });

  eleventyConfig.addPassthroughCopy({ "src/assets": "assets" });
  eleventyConfig.addFilter("renderMarkdown", (value) => md.render(String(value || "")));
  eleventyConfig.addFilter("inc", (n) => Number(n) + 1);
  eleventyConfig.addFilter("dec", (n) => Number(n) - 1);
  eleventyConfig.addFilter("at", (arr, index) => {
    if (!Array.isArray(arr)) return undefined;
    return arr[Number(index)];
  });

  return {
    pathPrefix: pagesPrefix(),
    dir: {
      input: "src",
      output: "dist",
      includes: "_includes",
    },
    htmlTemplateEngine: "liquid",
    markdownTemplateEngine: "liquid",
  };
};
