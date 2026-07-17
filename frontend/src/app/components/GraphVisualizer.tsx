"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import * as d3 from "d3";

interface Node extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  type: "document" | "entity";
  entity_type?: string;
  doc_id?: string;
  metadata?: {
    source_path?: string;
    created_at?: string;
    file_type?: string;
  };
}

interface Edge extends d3.SimulationLinkDatum<Node> {
  id: string;
  source: string | Node;
  target: string | Node;
  label: string;
  type: "relationship" | "mention";
}

interface GraphVisualizerProps {
  nodes: Node[];
  edges: Edge[];
  onNodeSelect: (node: Node | null) => void;
  selectedNode: Node | null;
}

const ENTITY_COLORS: Record<string, string> = {
  PERSON: "#a78bfa", // Violet
  ORGANIZATION: "#fbbf24", // Amber
  LOCATION: "#34d399", // Emerald
  EVENT: "#60a5fa", // Blue
  CONCEPT: "#22d3ee", // Cyan
  DATE: "#f472b6", // Pink
};

const DEFAULT_ENTITY_COLOR = "#a1a1aa"; // Zinc
const DOCUMENT_COLOR = "#06b6d4"; // Teal/Cyan

export default function GraphVisualizer({
  nodes,
  edges,
  onNodeSelect,
  selectedNode,
}: GraphVisualizerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Search and Filter States
  const [searchQuery, setSearchQuery] = useState("");
  const [showDocuments, setShowDocuments] = useState(true);
  const [showMentions, setShowMentions] = useState(true);
  const [selectedEntityTypes, setSelectedEntityTypes] = useState<Record<string, boolean>>({});

  // Get all unique entity types for filtering
  const allEntityTypes = useMemo(() => {
    const types = new Set<string>();
    nodes.forEach((n) => {
      if (n.type === "entity" && n.entity_type) {
        types.add(n.entity_type);
      }
    });
    return Array.from(types);
  }, [nodes]);

  // Initialize entity types filter state
  useEffect(() => {
    const initial: Record<string, boolean> = {};
    allEntityTypes.forEach((t) => {
      initial[t] = true;
    });
    setSelectedEntityTypes(initial);
  }, [allEntityTypes]);

  // Filter nodes & edges based on settings
  const { filteredNodes, filteredEdges } = useMemo(() => {
    const activeNodes = nodes.filter((n) => {
      if (n.type === "document") return showDocuments;
      if (n.type === "entity") {
        return n.entity_type ? selectedEntityTypes[n.entity_type] !== false : true;
      }
      return true;
    });

    const activeNodeIds = new Set(activeNodes.map((n) => n.id));

    const activeEdges = edges.filter((e) => {
      const sourceId = typeof e.source === "object" ? (e.source as Node).id : (e.source as string);
      const targetId = typeof e.target === "object" ? (e.target as Node).id : (e.target as string);

      if (!activeNodeIds.has(sourceId) || !activeNodeIds.has(targetId)) return false;
      if (e.type === "mention") return showMentions && showDocuments;
      return true;
    });

    return { filteredNodes: activeNodes, filteredEdges: activeEdges };
  }, [nodes, edges, showDocuments, showMentions, selectedEntityTypes]);

  // Autocomplete search suggestions
  const suggestions = useMemo(() => {
    if (!searchQuery.trim()) return [];
    return filteredNodes
      .filter((n) => n.label.toLowerCase().includes(searchQuery.toLowerCase()))
      .slice(0, 5);
  }, [searchQuery, filteredNodes]);

  useEffect(() => {
    if (!svgRef.current || !containerRef.current) return;

    const width = containerRef.current.clientWidth || 800;
    const height = containerRef.current.clientHeight || 600;

    const svg = d3.select(svgRef.current).attr("width", width).attr("height", height);
    svg.selectAll("*").remove(); // Clear previous rendering

    // Add marker defs for arrows on directed edges
    const defs = svg.append("defs");
    
    // Default relationship arrow
    defs.append("marker")
      .attr("id", "arrow-relationship")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 22) // Place arrow head at node border
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-5L10,0L0,5")
      .attr("fill", "#71717a");

    // Mentions arrow (optional, let's keep it simple without arrow for mentions)

    // Create main zoomable group
    const g = svg.append("g");

    // Zooming behaviour
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      });
    svg.call(zoom);

    // Deep copy data for D3 mutation
    const simNodes: Node[] = filteredNodes.map((n) => ({ ...n }));
    const simEdges: Edge[] = filteredEdges.map((e) => {
      const sourceId = typeof e.source === "object" ? (e.source as Node).id : (e.source as string);
      const targetId = typeof e.target === "object" ? (e.target as Node).id : (e.target as string);
      return { ...e, source: sourceId, target: targetId };
    });

    // Create force simulation
    const simulation = d3.forceSimulation<Node>(simNodes)
      .force("link", d3.forceLink<Node, Edge>(simEdges)
        .id((d) => d.id)
        .distance((d) => (d.type === "mention" ? 120 : 80))
      )
      .force("charge", d3.forceManyBody().strength(-150))
      .force("collide", d3.forceCollide().radius(30))
      .force("center", d3.forceCenter(width / 2, height / 2));

    // Render Edges
    const link = g.append("g")
      .attr("class", "links")
      .selectAll("g")
      .data(simEdges)
      .enter()
      .append("g")
      .attr("class", "link-group");

    const linkPath = link.append("line")
      .attr("stroke", (d) => (d.type === "mention" ? "#4b5563" : "#71717a"))
      .attr("stroke-width", (d) => (d.type === "mention" ? 1.5 : 2))
      .attr("stroke-dasharray", (d) => (d.type === "mention" ? "4,4" : "none"))
      .attr("marker-end", (d) => (d.type === "relationship" ? "url(#arrow-relationship)" : "none"))
      .attr("class", "cursor-pointer transition-opacity")
      .attr("opacity", 0.6);

    // Render Nodes
    const node = g.append("g")
      .attr("class", "nodes")
      .selectAll("g")
      .data(simNodes)
      .enter()
      .append("g")
      .attr("class", "node-group cursor-pointer")
      .on("click", (event, d) => {
        event.stopPropagation();
        onNodeSelect(nodes.find((originalNode) => originalNode.id === d.id) || null);
      })
      .call(
        d3.drag<SVGGElement, Node>()
          .on("start", dragstarted)
          .on("drag", dragged)
          .on("end", dragended)
      );

    // Node glowing filter
    const glowFilter = defs.append("filter")
      .attr("id", "glow")
      .attr("x", "-30%")
      .attr("y", "-30%")
      .attr("width", "160%")
      .attr("height", "160%");
    glowFilter.append("feGaussianBlur")
      .attr("stdDeviation", "4")
      .attr("result", "blur");
    glowFilter.append("feComposite")
      .attr("in", "SourceGraphic")
      .attr("in2", "blur")
      .attr("operator", "over");

    // Draw circles for nodes
    node.append("circle")
      .attr("r", (d) => (d.type === "document" ? 14 : 10))
      .attr("fill", (d) => {
        if (d.type === "document") return DOCUMENT_COLOR;
        return d.entity_type ? ENTITY_COLORS[d.entity_type] || DEFAULT_ENTITY_COLOR : DEFAULT_ENTITY_COLOR;
      })
      .attr("stroke", (d) => {
        if (selectedNode && d.id === selectedNode.id) return "#ffffff";
        return d.type === "document" ? "#0891b2" : "#52525b";
      })
      .attr("stroke-width", (d) => {
        if (selectedNode && d.id === selectedNode.id) return 3;
        return 1.5;
      })
      .attr("filter", (d) => (selectedNode && d.id === selectedNode.id ? "url(#glow)" : "none"))
      .attr("class", "transition-all duration-200");

    // Add labels to nodes
    node.append("text")
      .attr("dy", (d) => (d.type === "document" ? 22 : 18))
      .attr("text-anchor", "middle")
      .attr("class", "text-[10px] font-medium fill-zinc-300 pointer-events-none select-none font-sans drop-shadow-md")
      .text((d) => d.label);

    // Hover Highlight logic
    node.on("mouseover", function (event, d) {
      // Find connected nodes
      const connectedNodeIds = new Set<string>([d.id]);
      simEdges.forEach((e) => {
        if (e.source === d.id) connectedNodeIds.add(e.target as string);
        if (e.target === d.id) connectedNodeIds.add(e.source as string);
      });

      // Dim non-connected nodes & edges
      node.attr("opacity", (n) => (connectedNodeIds.has(n.id) ? 1.0 : 0.15));
      linkPath.attr("opacity", (e) => {
        const sId = typeof e.source === "object" ? (e.source as Node).id : (e.source as string);
        const tId = typeof e.target === "object" ? (e.target as Node).id : (e.target as string);
        return sId === d.id || tId === d.id ? 1.0 : 0.05;
      });
    });

    node.on("mouseout", function () {
      // Restore default opacities
      node.attr("opacity", 1.0);
      linkPath.attr("opacity", 0.6);
    });

    // Update positions on tick
    simulation.on("tick", () => {
      linkPath
        .attr("x1", (d) => (d.source as Node).x || 0)
        .attr("y1", (d) => (d.source as Node).y || 0)
        .attr("x2", (d) => (d.target as Node).x || 0)
        .attr("y2", (d) => (d.target as Node).y || 0);

      node.attr("transform", (d) => `translate(${d.x || 0}, ${d.y || 0})`);
    });

    // Handle center focusing on selection changes
    if (selectedNode) {
      const target = simNodes.find((n) => n.id === selectedNode.id);
      if (target && target.x !== undefined && target.y !== undefined) {
        svg.transition().duration(750).call(
          zoom.transform,
          d3.zoomIdentity.translate(width / 2 - target.x, height / 2 - target.y).scale(1.2)
        );
      }
    }

    // Drag methods
    function dragstarted(event: d3.D3DragEvent<SVGGElement, Node, Node>, d: Node) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    }

    function dragged(event: d3.D3DragEvent<SVGGElement, Node, Node>, d: Node) {
      d.fx = event.x;
      d.fy = event.y;
    }

    function dragended(event: d3.D3DragEvent<SVGGElement, Node, Node>, d: Node) {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    }

    return () => {
      simulation.stop();
    };
  }, [filteredNodes, filteredEdges, selectedNode, onNodeSelect, nodes]);

  // Center node when suggestion clicked
  const handleSuggestionClick = (node: Node) => {
    onNodeSelect(nodes.find((n) => n.id === node.id) || null);
    setSearchQuery("");
  };

  const resetZoom = () => {
    if (!svgRef.current || !containerRef.current) return;
    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight;
    d3.select(svgRef.current)
      .transition()
      .duration(500)
      .call(
        d3.zoom<SVGSVGElement, unknown>().transform,
        d3.zoomIdentity.translate(0, 0).scale(1)
      );
  };

  return (
    <div className="relative flex flex-1 overflow-hidden" ref={containerRef}>
      {/* Interactive Controls Overlay */}
      <div className="absolute top-4 left-4 z-10 w-64 rounded-2xl border border-zinc-700/60 bg-zinc-900/90 p-4 shadow-xl backdrop-blur-md space-y-4">
        {/* Search */}
        <div className="relative">
          <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500 mb-1.5">
            Search Entity / File
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:border-cyan-500 focus:outline-none"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-2 top-[24px] text-zinc-500 hover:text-zinc-300 text-xs"
              >
                ✕
              </button>
            )}
          </div>
          {/* Autocomplete Suggestions */}
          {suggestions.length > 0 && (
            <div className="absolute left-0 right-0 mt-1 max-h-48 overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-800 shadow-2xl">
              {suggestions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => handleSuggestionClick(s)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
                >
                  <div
                    className="h-2 w-2 rounded-full"
                    style={{
                      backgroundColor:
                        s.type === "document"
                          ? DOCUMENT_COLOR
                          : s.entity_type
                          ? ENTITY_COLORS[s.entity_type] || DEFAULT_ENTITY_COLOR
                          : DEFAULT_ENTITY_COLOR,
                    }}
                  />
                  <span className="truncate">{s.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Filters */}
        <div>
          <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500 mb-2">
            Filters
          </label>
          <div className="space-y-1.5">
            <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
              <input
                type="checkbox"
                checked={showDocuments}
                onChange={(e) => setShowDocuments(e.target.checked)}
                className="accent-cyan-500 h-3.5 w-3.5 rounded border-zinc-700 bg-zinc-800"
              />
              Show Documents (Files)
            </label>
            <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
              <input
                type="checkbox"
                checked={showMentions}
                onChange={(e) => setShowMentions(e.target.checked)}
                className="accent-cyan-500 h-3.5 w-3.5 rounded border-zinc-700 bg-zinc-800"
                disabled={!showDocuments}
              />
              Show Document Mentions
            </label>
          </div>
        </div>

        {/* Entity Types */}
        {allEntityTypes.length > 0 && (
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500 mb-2">
              Entity Types
            </label>
            <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
              {allEntityTypes.map((type) => (
                <label key={type} className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedEntityTypes[type] !== false}
                    onChange={(e) => {
                      setSelectedEntityTypes((prev) => ({
                        ...prev,
                        [type]: e.target.checked,
                      }));
                    }}
                    className="h-3.5 w-3.5 rounded border-zinc-700 bg-zinc-800"
                    style={{ accentColor: ENTITY_COLORS[type] || DEFAULT_ENTITY_COLOR }}
                  />
                  <div
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: ENTITY_COLORS[type] || DEFAULT_ENTITY_COLOR }}
                  />
                  <span>{type}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        {/* Zoom Control */}
        <div className="pt-2 border-t border-zinc-800 flex justify-between">
          <button
            onClick={resetZoom}
            className="cursor-pointer rounded-lg border border-zinc-700 bg-zinc-800/80 px-2.5 py-1 text-[10px] font-medium text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
          >
            Reset View
          </button>
          <span className="text-[9px] text-zinc-600 self-center">Drag to pan / Scroll to zoom</span>
        </div>
      </div>

      {/* SVG Canvas */}
      <svg ref={svgRef} className="h-full w-full bg-zinc-950/20" />
    </div>
  );
}
