import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { IconMinus, IconPlus } from './icons'
import '../styles/schema-diagram.css'

const NODE_WIDTH = 260
const NODE_HEIGHT = 220
const GAP_X = 60
const GAP_Y = 54

function escapeXml(value) {
  return String(value ?? '').replace(/[<>&'"]/g, (character) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' }[character]))
}

const SchemaDiagram = forwardRef(function SchemaDiagram({ schema }, ref) {
  const viewportRef = useRef(null)
  const [zoom, setZoom] = useState(1)
  const [positions, setPositions] = useState({})
  const [drag, setDrag] = useState(null)
  const tablePositions = useMemo(() => schema.tables.reduce((result, table, index) => {
    const columns = Math.max(1, Math.ceil(Math.sqrt(schema.tables.length)))
    result[table.name] = { x: (index % columns) * (NODE_WIDTH + GAP_X) + 28, y: Math.floor(index / columns) * (NODE_HEIGHT + GAP_Y) + 28 }
    return result
  }, {}), [schema])
  const currentPositions = useMemo(() => ({ ...tablePositions, ...positions }), [positions, tablePositions])
  const columns = Math.max(1, Math.ceil(Math.sqrt(schema.tables.length)))
  const rows = Math.max(1, Math.ceil(schema.tables.length / columns))
  const width = Math.max(900, columns * (NODE_WIDTH + GAP_X) + 56)
  const height = Math.max(520, rows * (NODE_HEIGHT + GAP_Y) + 56)

  useEffect(() => {
    setPositions({})
    setZoom(1)
  }, [schema])

  useEffect(() => {
    if (!drag) return undefined
    function move(event) {
      setPositions((current) => ({ ...current, [drag.name]: { x: drag.origin.x + (event.clientX - drag.startX) / zoom, y: drag.origin.y + (event.clientY - drag.startY) / zoom } }))
    }
    function stop() { setDrag(null) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop) }
  }, [drag, zoom])

  useImperativeHandle(ref, () => ({
    download() {
      const header = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#f8faff"/>`
      const edges = schema.relationships.map((relation) => {
        const from = currentPositions[relation.fromTable]
        const to = currentPositions[relation.toTable]
        if (!from || !to) return ''
        return `<line x1="${from.x + NODE_WIDTH / 2}" y1="${from.y + NODE_HEIGHT / 2}" x2="${to.x + NODE_WIDTH / 2}" y2="${to.y + NODE_HEIGHT / 2}" stroke="#7c8baa" stroke-width="2"/><text x="${(from.x + to.x) / 2 + NODE_WIDTH / 2}" y="${(from.y + to.y) / 2 + NODE_HEIGHT / 2 - 4}" fill="#596985" font-size="11">${escapeXml(relation.cardinality)}</text>`
      }).join('')
      const nodes = schema.tables.map((table) => { const position = currentPositions[table.name]; return `<g><rect x="${position.x}" y="${position.y}" width="${NODE_WIDTH}" height="${NODE_HEIGHT}" rx="10" fill="#fff" stroke="#dbe3f1"/><rect x="${position.x}" y="${position.y}" width="${NODE_WIDTH}" height="38" rx="10" fill="#eef4ff"/><text x="${position.x + 14}" y="${position.y + 24}" fill="#1d3d76" font-size="14" font-weight="700">${escapeXml(table.name)}</text>${table.columns.slice(0, 8).map((column, index) => `<text x="${position.x + 14}" y="${position.y + 62 + index * 18}" fill="#35445f" font-size="11">${escapeXml(column.name)} · ${escapeXml(column.type)}</text>`).join('')}</g>` }).join('')
      const blob = new Blob([`${header}${edges}${nodes}</svg>`], { type: 'image/svg+xml' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'schema-diagram.svg'; document.body.appendChild(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 0)
    },
  }), [currentPositions, height, schema, width])

  return <div className="schema-diagram-shell"><div className="schema-diagram-toolbar"><span>{schema.tables.length} tables · {schema.relationships.length} relationships</span><div><button type="button" onClick={() => setZoom((value) => Math.max(.65, value - .1))} aria-label="Zoom out"><IconMinus aria-hidden="true" /></button><b>{Math.round(zoom * 100)}%</b><button type="button" onClick={() => setZoom((value) => Math.min(1.5, value + .1))} aria-label="Zoom in"><IconPlus aria-hidden="true" /></button></div></div><div className="schema-diagram-viewport" ref={viewportRef}><div className="schema-diagram-canvas" style={{ width, height, transform: `scale(${zoom})`, transformOrigin: 'top left' }}><svg className="schema-diagram-edges" width={width} height={height} aria-hidden="true">{schema.relationships.map((relation) => { const from = currentPositions[relation.fromTable]; const to = currentPositions[relation.toTable]; if (!from || !to) return null; return <g key={relation.id}><line x1={from.x + NODE_WIDTH / 2} y1={from.y + NODE_HEIGHT / 2} x2={to.x + NODE_WIDTH / 2} y2={to.y + NODE_HEIGHT / 2} /><text x={(from.x + to.x) / 2 + NODE_WIDTH / 2} y={(from.y + to.y) / 2 + NODE_HEIGHT / 2 - 6}>{relation.cardinality}</text></g> })}</svg>{schema.tables.map((table) => { const position = currentPositions[table.name]; return <article className="schema-diagram-node" key={table.name} style={{ left: position.x, top: position.y, width: NODE_WIDTH, minHeight: NODE_HEIGHT }} onPointerDown={(event) => { if (event.button === 0) setDrag({ name: table.name, startX: event.clientX, startY: event.clientY, origin: position }) }}><header>{table.name}</header><div className="schema-diagram-columns">{table.columns.map((column) => <div key={column.name}><strong className={column.primaryKey ? 'is-primary' : ''}>{column.primaryKey ? 'PK ' : ''}{column.name}</strong><span>{column.type}{column.reference ? ` → ${column.reference.table}.${column.reference.column}` : ''}</span></div>)}</div></article> })}</div></div></div>
})

export default SchemaDiagram
