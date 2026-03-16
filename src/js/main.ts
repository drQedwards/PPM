/// <reference types="d3-force" />
/// <reference types="d3-selection" />
/// <reference types="d3-zoom" />
/// <reference types="d3-drag" />

/**
 * main.ts — PPM Dependency Graph Visualizer
 *
 * Renders the PPM dependency lattice as an interactive D3 force-directed
 * graph.  Each node represents a package; edges represent dependencies.
 *
 * Architecture mirrors the PMLL memory-silo model:
 *   - Node positions are stored in-memory as a flat array (silo).
 *   - The force simulation iterates like `pml_logic_loop` in PMLL.c.
 *
 * Entry point: `renderDependencyGraph()` — called from the page bootstrap below.
 */

import { forceSimulation, forceLink, forceManyBody, forceCenter, SimulationNodeDatum, SimulationLinkDatum } from "d3-force";
import { select, Selection } from "d3-selection";
import { zoom, zoomIdentity } from "d3-zoom";
import { drag } from "d3-drag";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A package node in the dependency graph. */
interface PackageNode extends SimulationNodeDatum {
  id: string;
  version: string;
  /** Optional depth from root (0 = direct dependency). */
  depth?: number;
}

/** A directed dependency edge. */
interface DepLink extends SimulationLinkDatum<PackageNode> {
  source: string | PackageNode;
  target: string | PackageNode;
}

/** Shape of the serialised graph data embedded in the page. */
interface GraphData {
  nodes: PackageNode[];
  links: DepLink[];
}

// ---------------------------------------------------------------------------
// Graph renderer
// ---------------------------------------------------------------------------

/**
 * Render the PPM dependency graph inside `container`.
 *
 * @param container  CSS selector or DOM element for the SVG mount point.
 * @param data       Serialised graph (nodes + links).
 */
export function renderDependencyGraph(
  container: string | Element,
  data: GraphData,
): void {
  const root = typeof container === "string"
    ? document.querySelector<Element>(container)
    : container;
  if (!root) {
    console.warn("renderDependencyGraph: container not found");
    return;
  }

  const width = (root as HTMLElement).clientWidth || 800;
  const height = (root as HTMLElement).clientHeight || 600;

  /* Create SVG canvas */
  const svg = select(root)
    .append("svg")
    .attr("width", "100%")
    .attr("height", "100%")
    .attr("viewBox", `0 0 ${width} ${height}`);

  const g = svg.append("g").attr("class", "graph-layer");

  /* Zoom + pan */
  const zoomBehaviour = zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.2, 8])
    .on("zoom", (event) => g.attr("transform", event.transform));
  (svg as Selection<SVGSVGElement, unknown, null, undefined>).call(zoomBehaviour);

  /* Force simulation — mirrors PMLL's Ouroboros update loop */
  const simulation = forceSimulation<PackageNode>(data.nodes)
    .force("link", forceLink<PackageNode, DepLink>(data.links)
      .id((d) => d.id)
      .distance(80))
    .force("charge", forceManyBody().strength(-300))
    .force("center", forceCenter(width / 2, height / 2));

  /* Draw edges */
  const link = g.append("g")
    .attr("class", "links")
    .selectAll("line")
    .data(data.links)
    .join("line")
    .attr("stroke", "#aaa")
    .attr("stroke-width", 1.5);

  /* Draw nodes */
  const node = g.append("g")
    .attr("class", "nodes")
    .selectAll<SVGGElement, PackageNode>("g")
    .data(data.nodes)
    .join("g")
    .attr("class", "node")
    .call(
      drag<SVGGElement, PackageNode>()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        }),
    );

  node.append("circle")
    .attr("r", 10)
    .attr("fill", (d) => (d.depth === 0 ? "#4f8ef7" : "#ccc"))
    .attr("stroke", "#333")
    .attr("stroke-width", 1);

  node.append("text")
    .attr("dy", "0.31em")
    .attr("x", 14)
    .text((d) => `${d.id}@${d.version}`)
    .style("font-size", "11px");

  /* Tick update — analogous to pml_refine() stepping the assignment lattice */
  simulation.on("tick", () => {
    link
      .attr("x1", (d) => (d.source as PackageNode).x ?? 0)
      .attr("y1", (d) => (d.source as PackageNode).y ?? 0)
      .attr("x2", (d) => (d.target as PackageNode).x ?? 0)
      .attr("y2", (d) => (d.target as PackageNode).y ?? 0);

    node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
  });
}

// ---------------------------------------------------------------------------
// Page bootstrap
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  const dataEl = document.getElementById("graph-data");
  if (!dataEl) return;

  let graphData: GraphData;
  try {
    graphData = JSON.parse(dataEl.textContent ?? "{}") as GraphData;
  } catch {
    console.error("Failed to parse graph data");
    return;
  }

  renderDependencyGraph("#graph-container", graphData);
});
