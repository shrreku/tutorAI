import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2, RotateCcw, Trash2 } from 'lucide-react'
import {
  useDeleteResource,
  useResourceKnowledgeBase,
  useRetryIngestion,
} from '../api/hooks'
import type { KnowledgeBaseConcept, KnowledgeBaseEdge } from '../types/api'

const GRAPH_WIDTH = 1280
const GRAPH_HEIGHT = 760
const EDGE_COLOR = '#67E8F9'
const EDGE_LABEL_COLOR = '#CFFAFE'
const NODE_FILL = '#0E7490'
const NODE_STROKE = '#67E8F9'
const NODE_LABEL_COLOR = '#E0F2FE'
const SELECTED_NODE_FILL = '#7C3AED'
const SELECTED_NODE_STROKE = '#DDD6FE'
const SELECTED_NODE_LABEL = '#F5F3FF'

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function truncateLabel(value: string, maxLength = 18): string {
  if (value.length <= maxLength) return value
  return `${value.slice(0, maxLength - 1)}…`
}

function edgeKey(edge: Pick<KnowledgeBaseEdge, 'source_concept_id' | 'target_concept_id' | 'relation_type'>): string {
  return `${edge.source_concept_id}::${edge.target_concept_id}::${edge.relation_type.toUpperCase()}`
}

function undirectedPairKey(left: string, right: string): string {
  return left < right ? `${left}::${right}` : `${right}::${left}`
}

function conceptImportance(concept: KnowledgeBaseConcept): number {
  return typeof concept.importance_score === 'number' ? concept.importance_score : 0
}

export default function ResourceKnowledgeBasePage() {
  const navigate = useNavigate()
  const { id } = useParams<{ id: string }>()

  const { data, isLoading, error } = useResourceKnowledgeBase(id ?? '')
  const retryMutation = useRetryIngestion()
  const deleteMutation = useDeleteResource()

  const [selectedConceptId, setSelectedConceptId] = useState('')
  const [manualNodePositions, setManualNodePositions] = useState<Record<string, { x: number; y: number }>>({})
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null)
  const [isPanning, setIsPanning] = useState(false)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [hoveredEdgeKey, setHoveredEdgeKey] = useState<string | null>(null)

  const svgRef = useRef<SVGSVGElement | null>(null)
  const panStartRef = useRef<{ clientX: number; clientY: number; panX: number; panY: number } | null>(null)

  const concepts = useMemo(() => data?.concepts ?? [], [data])
  const edges = useMemo(() => data?.edges ?? [], [data])

  useEffect(() => {
    if (!concepts.length) {
      setSelectedConceptId('')
      return
    }
    if (!selectedConceptId || !concepts.some((item) => item.concept_id === selectedConceptId)) {
      setSelectedConceptId(concepts[0].concept_id)
    }
  }, [concepts, selectedConceptId])

  useEffect(() => {
    setManualNodePositions((prev) => {
      const ids = new Set(concepts.map((item) => item.concept_id))
      const next: Record<string, { x: number; y: number }> = {}
      for (const [key, value] of Object.entries(prev)) {
        if (ids.has(key)) next[key] = value
      }
      return next
    })
  }, [concepts])

  const summary = useMemo(() => {
    if (!data) return null
    return `${data.chunk_count} chunks • ${concepts.length} concepts • ${edges.length} graph edges`
  }, [data, concepts.length, edges.length])

  const treeLayout = useMemo(() => {
    if (concepts.length === 0) {
      return {
        nodes: [] as Array<{ concept: KnowledgeBaseConcept; x: number; y: number; radius: number }>,
        treePairs: new Set<string>(),
      }
    }

    const conceptById = new Map(concepts.map((item) => [item.concept_id, item]))
    const conceptIds = concepts.map((item) => item.concept_id)

    const adjacency = new Map<string, Set<string>>()
    for (const id of conceptIds) {
      adjacency.set(id, new Set())
    }
    for (const edge of edges) {
      if (!adjacency.has(edge.source_concept_id) || !adjacency.has(edge.target_concept_id)) continue
      adjacency.get(edge.source_concept_id)?.add(edge.target_concept_id)
      adjacency.get(edge.target_concept_id)?.add(edge.source_concept_id)
    }

    const importanceValues = concepts
      .map((item) => item.importance_score)
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
    const minImportance = importanceValues.length ? Math.min(...importanceValues) : 0
    const maxImportance = importanceValues.length ? Math.max(...importanceValues) : 1
    const spread = maxImportance - minImportance || 1

    const nodeRadiusById = new Map<string, number>()
    for (const concept of concepts) {
      const normalizedImportance =
        typeof concept.importance_score === 'number'
          ? (concept.importance_score - minImportance) / spread
          : 0.45
      const radius = 20 + normalizedImportance * 26
      nodeRadiusById.set(concept.concept_id, radius)
    }

    const sortedByImportance = [...concepts]
      .sort((left, right) => conceptImportance(right) - conceptImportance(left))
      .map((item) => item.concept_id)

    const unvisited = new Set(sortedByImportance)
    const components: string[][] = []
    while (unvisited.size > 0) {
      const start = [...unvisited][0]
      const queue = [start]
      const component: string[] = []
      unvisited.delete(start)
      while (queue.length > 0) {
        const current = queue.shift()!
        component.push(current)
        const neighbors = [...(adjacency.get(current) ?? [])]
        neighbors.sort((left, right) => {
          const leftConcept = conceptById.get(left)
          const rightConcept = conceptById.get(right)
          return conceptImportance(rightConcept!) - conceptImportance(leftConcept!)
        })
        for (const neighbor of neighbors) {
          if (!unvisited.has(neighbor)) continue
          unvisited.delete(neighbor)
          queue.push(neighbor)
        }
      }
      components.push(component)
    }

    components.sort((left, right) => {
      const leftMax = Math.max(...left.map((id) => conceptImportance(conceptById.get(id)!)))
      const rightMax = Math.max(...right.map((id) => conceptImportance(conceptById.get(id)!)))
      return rightMax - leftMax
    })

    const treePairs = new Set<string>()
    const nodes: Array<{ concept: KnowledgeBaseConcept; x: number; y: number; radius: number }> = []

    const verticalMargin = 38
    const availableHeight = GRAPH_HEIGHT - verticalMargin * 2
    const componentBandHeight = Math.max(170, availableHeight / Math.max(1, components.length))

    for (let componentIndex = 0; componentIndex < components.length; componentIndex += 1) {
      const component = components[componentIndex]
      if (component.length === 0) continue

      const root = [...component].sort(
        (left, right) => conceptImportance(conceptById.get(right)!) - conceptImportance(conceptById.get(left)!),
      )[0]

      const parent = new Map<string, string | null>()
      const depth = new Map<string, number>()
      const children = new Map<string, string[]>()
      for (const id of component) {
        children.set(id, [])
      }

      const queue = [root]
      parent.set(root, null)
      depth.set(root, 0)

      while (queue.length > 0) {
        const current = queue.shift()!
        const neighbors = [...(adjacency.get(current) ?? [])].filter((id) => component.includes(id))
        neighbors.sort((left, right) => {
          const leftTopo = conceptById.get(left)?.topo_order
          const rightTopo = conceptById.get(right)?.topo_order
          if (leftTopo != null && rightTopo != null && leftTopo !== rightTopo) return leftTopo - rightTopo
          return conceptImportance(conceptById.get(right)!) - conceptImportance(conceptById.get(left)!)
        })

        for (const neighbor of neighbors) {
          if (parent.has(neighbor)) continue
          parent.set(neighbor, current)
          depth.set(neighbor, (depth.get(current) ?? 0) + 1)
          children.get(current)?.push(neighbor)
          treePairs.add(undirectedPairKey(current, neighbor))
          queue.push(neighbor)
        }
      }

      for (const id of component) {
        if (parent.has(id)) continue
        parent.set(id, null)
        depth.set(id, 0)
      }

      const levels = new Map<number, string[]>()
      let maxDepth = 0
      for (const id of component) {
        const level = depth.get(id) ?? 0
        if (!levels.has(level)) levels.set(level, [])
        levels.get(level)?.push(id)
        if (level > maxDepth) maxDepth = level
      }

      const bandTop = verticalMargin + componentIndex * componentBandHeight
      const bandBottom = bandTop + componentBandHeight
      const bandCenterY = (bandTop + bandBottom) / 2
      const levelHeight = maxDepth > 0 ? Math.min(120, (componentBandHeight - 40) / (maxDepth + 1)) : 0
      const topForLevels = bandCenterY - (maxDepth * levelHeight) / 2

      for (let level = 0; level <= maxDepth; level += 1) {
        const idsAtLevel = levels.get(level) ?? []
        idsAtLevel.sort((left, right) => {
          const leftChildren = children.get(left)?.length ?? 0
          const rightChildren = children.get(right)?.length ?? 0
          if (leftChildren !== rightChildren) return rightChildren - leftChildren
          return conceptImportance(conceptById.get(right)!) - conceptImportance(conceptById.get(left)!)
        })

        const y = maxDepth > 0 ? topForLevels + level * levelHeight : bandCenterY
        const count = idsAtLevel.length
        if (count === 0) continue

        for (let i = 0; i < count; i += 1) {
          const conceptId = idsAtLevel[i]
          const concept = conceptById.get(conceptId)
          if (!concept) continue
          const radius = nodeRadiusById.get(conceptId) ?? 22
          const x = count === 1
            ? GRAPH_WIDTH / 2
            : 80 + (i * (GRAPH_WIDTH - 160)) / (count - 1)

          nodes.push({
            concept,
            x: manualNodePositions[conceptId]?.x ?? x,
            y: manualNodePositions[conceptId]?.y ?? y,
            radius,
          })
        }
      }
    }

    return {
      nodes,
      treePairs,
    }
  }, [concepts, edges, manualNodePositions])

  const graphNodes = useMemo(() => treeLayout.nodes, [treeLayout])
  const treePairs = useMemo(() => treeLayout.treePairs, [treeLayout])

  const graphNodeById = useMemo(
    () => new Map(graphNodes.map((node) => [node.concept.concept_id, node])),
    [graphNodes],
  )

  const graphEdges = useMemo(() => {
    return edges
      .map((edge) => {
        const source = graphNodeById.get(edge.source_concept_id)
        const target = graphNodeById.get(edge.target_concept_id)
        if (!source || !target) {
          return null
        }

        const dx = target.x - source.x
        const dy = target.y - source.y
        const distance = Math.sqrt(dx * dx + dy * dy) || 1
        const unitX = dx / distance
        const unitY = dy / distance

        const x1 = source.x + unitX * (source.radius + 3)
        const y1 = source.y + unitY * (source.radius + 3)
        const x2 = target.x - unitX * (target.radius + 9)
        const y2 = target.y - unitY * (target.radius + 9)

        return {
          ...edge,
          x1,
          y1,
          x2,
          y2,
          labelX: (x1 + x2) / 2,
          labelY: (y1 + y2) / 2,
          isTree: treePairs.has(undirectedPairKey(edge.source_concept_id, edge.target_concept_id)),
        }
      })
      .filter((item): item is KnowledgeBaseEdge & {
        x1: number;
        y1: number;
        x2: number;
        y2: number;
        labelX: number;
        labelY: number;
          isTree: boolean;
      } => item !== null)
        }, [edges, graphNodeById, treePairs])

  const selectedNeighborIds = useMemo(() => {
    if (!selectedConceptId) return new Set<string>()
    const ids = new Set<string>([selectedConceptId])
    for (const edge of edges) {
      if (edge.source_concept_id === selectedConceptId) ids.add(edge.target_concept_id)
      if (edge.target_concept_id === selectedConceptId) ids.add(edge.source_concept_id)
    }
    return ids
  }, [edges, selectedConceptId])

  const getSvgCoordinates = (clientX: number, clientY: number): { x: number; y: number } | null => {
    if (!svgRef.current) return null
    const rect = svgRef.current.getBoundingClientRect()
    if (!rect.width || !rect.height) return null
    const viewX = ((clientX - rect.left) / rect.width) * GRAPH_WIDTH
    const viewY = ((clientY - rect.top) / rect.height) * GRAPH_HEIGHT
    return {
      x: (viewX - pan.x) / zoom,
      y: (viewY - pan.y) / zoom,
    }
  }

  const handleGraphWheel: React.WheelEventHandler<SVGSVGElement> = (event) => {
    event.preventDefault()
    const delta = event.deltaY > 0 ? -0.1 : 0.1
    setZoom((prev) => clamp(prev + delta, 0.55, 2.4))
  }

  const handleGraphMouseDown: React.MouseEventHandler<SVGSVGElement> = (event) => {
    if (event.button !== 0) return
    setIsPanning(true)
    panStartRef.current = {
      clientX: event.clientX,
      clientY: event.clientY,
      panX: pan.x,
      panY: pan.y,
    }
  }

  const handleGraphMouseMove: React.MouseEventHandler<SVGSVGElement> = (event) => {
    if (draggingNodeId) {
      const point = getSvgCoordinates(event.clientX, event.clientY)
      if (!point) return
      const targetNode = graphNodeById.get(draggingNodeId)
      if (!targetNode) return
      setManualNodePositions((prev) => ({
        ...prev,
        [draggingNodeId]: {
          x: clamp(point.x, targetNode.radius + 16, GRAPH_WIDTH - targetNode.radius - 16),
          y: clamp(point.y, targetNode.radius + 16, GRAPH_HEIGHT - targetNode.radius - 16),
        },
      }))
      return
    }

    if (!isPanning || !panStartRef.current) return
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect?.width || !rect.height) return
    const scaleX = GRAPH_WIDTH / rect.width
    const scaleY = GRAPH_HEIGHT / rect.height
    setPan({
      x: panStartRef.current.panX + (event.clientX - panStartRef.current.clientX) * scaleX,
      y: panStartRef.current.panY + (event.clientY - panStartRef.current.clientY) * scaleY,
    })
  }

  const handleGraphMouseUp: React.MouseEventHandler<SVGSVGElement> = () => {
    setDraggingNodeId(null)
    setIsPanning(false)
    panStartRef.current = null
  }

  const resetGraphView = () => {
    setPan({ x: 0, y: 0 })
    setZoom(1)
    setManualNodePositions({})
  }

  const handleRetry = async () => {
    if (!id) return
    await retryMutation.mutateAsync(id)
  }

  const handleDelete = async () => {
    if (!id || !data) return
    const confirmed = window.confirm(`Delete resource "${data.resource_name}" and all knowledge-base data?`)
    if (!confirmed) return
    await deleteMutation.mutateAsync(id)
    navigate('/resources')
  }

  if (!id) {
    return <div className="p-8 text-sm text-destructive">Invalid resource ID</div>
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-gold animate-spin" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="p-8">
        <div className="p-4 rounded-xl border border-destructive/30 bg-destructive/10 text-sm text-destructive">
          Failed to load resource knowledge base.
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <button
            onClick={() => navigate('/resources')}
            className="mb-3 inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Resources
          </button>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">
            {data.resource_name}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">{summary}</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleRetry}
            disabled={retryMutation.isPending || data.status === 'processing' || data.status === 'pending'}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gold/30 text-gold text-sm hover:bg-gold/10 disabled:opacity-50"
          >
            <RotateCcw className={`w-4 h-4 ${retryMutation.isPending ? 'animate-spin' : ''}`} />
            Retry Ingestion
          </button>
          <button
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-red-400/40 text-red-300 text-sm hover:bg-red-400/10 disabled:opacity-50"
          >
            <Trash2 className="w-4 h-4" />
            Delete
          </button>
        </div>
      </div>

      <section className="flex-1 rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-display text-lg font-semibold text-foreground">Knowledge Graph</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setZoom((prev) => clamp(prev - 0.1, 0.55, 2.4))}
              className="text-[11px] px-2 py-1 rounded border border-border text-muted-foreground hover:text-foreground"
            >
              −
            </button>
            <button
              onClick={() => setZoom((prev) => clamp(prev + 0.1, 0.55, 2.4))}
              className="text-[11px] px-2 py-1 rounded border border-border text-muted-foreground hover:text-foreground"
            >
              +
            </button>
            <button
              onClick={resetGraphView}
              className="text-[11px] px-2 py-1 rounded border border-border text-muted-foreground hover:text-foreground"
            >
              Reset
            </button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground mb-4">Scroll to zoom, drag background to pan, drag node to reposition. Node size scales by importance.</p>

        <div className="rounded-md border border-border/60 bg-background/60 overflow-hidden h-[76vh] min-h-[560px]">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`}
            className="w-full h-full"
            onWheel={handleGraphWheel}
            onMouseDown={handleGraphMouseDown}
            onMouseMove={handleGraphMouseMove}
            onMouseUp={handleGraphMouseUp}
            onMouseLeave={handleGraphMouseUp}
          >
            <defs>
              <marker id="graph-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
                <path d="M0,0 L0,6 L9,3 z" fill={EDGE_COLOR} fillOpacity={0.9} />
              </marker>
            </defs>

            <rect x={0} y={0} width={GRAPH_WIDTH} height={GRAPH_HEIGHT} fill="transparent" />

            <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
              {graphEdges.map((edge) => {
                const key = edgeKey(edge)
                const isIncidentToSelection =
                  selectedConceptId.length > 0 &&
                  (edge.source_concept_id === selectedConceptId || edge.target_concept_id === selectedConceptId)
                const shouldRender = edge.isTree || isIncidentToSelection
                if (!shouldRender) {
                  return null
                }
                const showLabel = hoveredEdgeKey === key || isIncidentToSelection
                return (
                  <g key={key} onMouseEnter={() => setHoveredEdgeKey(key)} onMouseLeave={() => setHoveredEdgeKey(null)}>
                    <line
                      x1={edge.x1}
                      y1={edge.y1}
                      x2={edge.x2}
                      y2={edge.y2}
                      stroke={EDGE_COLOR}
                      strokeWidth={isIncidentToSelection ? 2.6 : 1.7}
                      opacity={selectedConceptId && !isIncidentToSelection ? 0.28 : 0.88}
                      markerEnd="url(#graph-arrow)"
                    />
                    {showLabel && (
                      <text
                        x={edge.labelX}
                        y={edge.labelY - 4}
                        textAnchor="middle"
                        fill={EDGE_LABEL_COLOR}
                        fillOpacity={0.95}
                        fontSize={10}
                      >
                        {edge.relation_type}
                      </text>
                    )}
                  </g>
                )
              })}

              {graphNodes.map((node) => {
                const conceptId = node.concept.concept_id
                const isSelected = selectedConceptId === conceptId
                const isNeighbor = selectedNeighborIds.has(conceptId)
                return (
                  <g
                    key={conceptId}
                    onClick={() => setSelectedConceptId(conceptId)}
                    onMouseDown={(event) => {
                      event.stopPropagation()
                      setDraggingNodeId(conceptId)
                    }}
                    className="cursor-pointer"
                    opacity={selectedConceptId && !isNeighbor ? 0.3 : 1}
                  >
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={node.radius}
                      fill={isSelected ? SELECTED_NODE_FILL : NODE_FILL}
                      fillOpacity={isSelected ? 0.62 : 0.5}
                      stroke={isSelected ? SELECTED_NODE_STROKE : NODE_STROKE}
                      strokeWidth={isSelected ? 3 : 1.8}
                    />
                    <text
                      x={node.x}
                      y={node.y}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fill={isSelected ? SELECTED_NODE_LABEL : NODE_LABEL_COLOR}
                      fontWeight={isSelected ? 600 : 500}
                      fontSize={Math.max(10, Math.min(14, node.radius * 0.42))}
                    >
                      {truncateLabel(conceptId)}
                    </text>
                    <title>{conceptId}</title>
                  </g>
                )
              })}
            </g>
          </svg>
        </div>
      </section>
    </div>
  )
}
