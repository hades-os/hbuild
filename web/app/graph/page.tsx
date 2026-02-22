'use client'

import '@xyflow/react/dist/style.css';
import { PackageGraph, PackageGraphEdge } from '@/app/models';
import useSWR from 'swr';
import fetcher from "@/app/fetcher";
import { Box, Typography } from '@mui/material';
import { Node, Edge, ReactFlow, useReactFlow } from '@xyflow/react';

import ELK, { ElkExtendedEdge, ElkNode, LayoutOptions } from 'elkjs';
import { useCallback, useEffect, useState } from 'react';

const elk = new ELK();
const elkOptions = {
  'elk.algorithm': 'layered',
  'elk.layered.spacing.nodeNodeBetweenLayers': '100',
  'elk.spacing.nodeNode': '80',
};

const getLayoutedElements = async(nodes: ElkNode[], edges: ElkExtendedEdge[], options: LayoutOptions = {}) => {
    const isHorizontal = options?.['elk.direction'] === 'RIGHT';
    const graph = {
        id: 'root',
        layoutOptions: options,
        children: nodes.map((node) => ({
        ...node,
        // Adjust the target and source handle positions based on the layout
        // direction.
        targetPosition: isHorizontal ? 'left' : 'top',
        sourcePosition: isHorizontal ? 'right' : 'bottom',
    
        // Hardcode a width and height for elk to use when layouting.
        width: 150,
        height: 50,
        })),
        edges: edges,
    };
    
    const layoutedGraph = await elk.layout(graph)
    return {
      nodes: layoutedGraph.children!.map((node) => ({
        id: node.id,
        data: {
            label: node.id
        },
        // React Flow expects a position property on the node instead of `x`
        // and `y` fields.
        position: { x: node.x!, y: node.y! },
      })),
 
      edges: layoutedGraph.edges!.map((edge) => ({
        id: edge.id,
        source: edge.sources[0],
        target: edge.targets[0]
      })),
    }  
};

export default () => {
    const [nodes, setNodes] = useState<Node[]>([]);
    const [edges, setEdges] = useState<Edge[]>([]);

    const { data, error, isLoading } = useSWR<PackageGraph>(
        'http://localhost:8000/api/graph',
        fetcher
    )

    useEffect(() => {
        if (!data)
            return
        const inNodes = data.nodes.map(node => ({
            "id": node,
            "data": {
                label: node
            },
            "position": {}
        }))

        const inEdges =  data.edges.map(({ source, dest }) => ({
            "id": `${source}-${dest}`,
            "sources": [source],
            "targets": [dest],
            "type": "smoothstep"
        }))

        const opts = { 'elk.direction': 'DOWN', ...elkOptions };
        getLayoutedElements(inNodes, inEdges, opts).then(
            ({ nodes: layoutedNodes, edges: layoutedEdges }) => {
                setNodes(layoutedNodes);
                setEdges(layoutedEdges);
            },
        );    
    }, [data])

    if (isLoading) {
        return <>
            <Typography
                variant='h6'
                >Loading dependency graph, please wait...</Typography>
        </>
    }

    if (error) {
        throw Error('Failed to load package data')
    }

    return (
        <div className="h-[calc(100vh-128px)]">
            <ReactFlow 
                colorMode="dark"
                
                nodes={nodes}
                edges={edges}
                fitView
            />
        </div>
    )
}