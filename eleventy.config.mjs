/**
 * eleventy.config.mjs — Eleventy configuration for the PPM website.
 *
 * Input:  src/
 * Output: dist/
 *
 * Passes CSS and the compiled JS bundle through as static assets.
 */

export default function (eleventyConfig) {
  /* Pass CSS and pre-built JS bundle straight through */
  eleventyConfig.addPassthroughCopy("src/css");
  eleventyConfig.addPassthroughCopy({ "dist/js": "js" });

  /* Default graph data for the dependency visualiser (dev placeholder) */
  eleventyConfig.addGlobalData("graphData", {
    nodes: [
      { id: "ppm", version: "0.0.3-dev", depth: 0 },
      { id: "mcp", version: "1.0.0", depth: 1 },
      { id: "d3-force", version: "3.0.0", depth: 1 },
      { id: "d3-selection", version: "3.0.0", depth: 2 },
    ],
    links: [
      { source: "ppm", target: "mcp" },
      { source: "ppm", target: "d3-force" },
      { source: "d3-force", target: "d3-selection" },
    ],
  });

  return {
    dir: {
      input: "src",
      output: "dist",
      includes: "_includes",
    },
    templateFormats: ["njk", "html", "md"],
    htmlTemplateEngine: "njk",
    markdownTemplateEngine: "njk",
  };
}
