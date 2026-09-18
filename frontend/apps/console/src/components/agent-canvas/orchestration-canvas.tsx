import * as React from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type NodeTypes,
  type NodeMouseHandler,
  type OnNodesChange,
  type OnEdgesChange,
  useReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { CustomNode } from "./custom-node";
import type { CanvasNode, CanvasEdge, CanvasNodeData } from "@/types/agent-graph";

const nodeTypes: NodeTypes = {
  task: CustomNode,
  agent: CustomNode,
  model: CustomNode,
  rag: CustomNode,
  tool: CustomNode,
  verification: CustomNode,
  approval: CustomNode,
  result: CustomNode,
};

interface OrchestrationCanvasProps {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  onNodesChange: OnNodesChange<CanvasNode>;
  onEdgesChange: OnEdgesChange<CanvasEdge>;
  selectedNodeId: string | null;
  onSelectNode: (nodeData: CanvasNodeData | null) => void;
}

const CanvasInner: React.FC<OrchestrationCanvasProps> = ({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  selectedNodeId,
  onSelectNode,
}) => {
  const { fitView } = useReactFlow();

  // Initial fit view
  React.useEffect(() => {
    const timer = setTimeout(() => {
      fitView({ padding: 0.2, duration: 400 });
    }, 100);
    return () => clearTimeout(timer);
  }, [fitView]);

  // Keyboard navigation: Escape clears selection
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onSelectNode(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onSelectNode]);

  const handleNodeClick: NodeMouseHandler = React.useCallback(
    (_event, node) => {
      onSelectNode((node.data as unknown as CanvasNodeData) || null);
    },
    [onSelectNode]
  );

  const handlePaneClick = React.useCallback(() => {
    onSelectNode(null);
  }, [onSelectNode]);

  // Highlight selected node
  const displayNodes = React.useMemo(() => {
    return nodes.map((n) => ({
      ...n,
      selected: n.id === selectedNodeId,
    }));
  }, [nodes, selectedNodeId]);

  // MiniMap node color mapper
  const nodeColor = React.useCallback((node: CanvasNode) => {
    switch (node.type) {
      case "task":
        return "#0284c7";
      case "agent":
        return "#6366f1";
      case "model":
        return "#a855f7";
      case "rag":
        return "#14b8a6";
      case "tool":
        return "#f59e0b";
      case "verification":
        return "#10b981";
      case "approval":
        return "#f43f5e";
      case "result":
        return "#3b82f6";
      default:
        return "#6b7280";
    }
  }, []);

  return (
    <div className="w-full h-full relative" data-testid="react-flow-canvas">
      <ReactFlow
        nodes={displayNodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={2.0}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: "smoothstep",
          style: { strokeWidth: 2 },
        }}
      >
        <Background gap={16} size={1} />
        <Controls
          showInteractive={false}
          className="bg-card border shadow-sm rounded-lg overflow-hidden"
        />
        <MiniMap
          nodeColor={nodeColor as (node: unknown) => string}
          zoomable
          pannable
          className="bg-card/90 border rounded-lg shadow-sm"
        />
      </ReactFlow>
    </div>
  );
};

export const OrchestrationCanvas: React.FC<OrchestrationCanvasProps> = (props) => {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
};
