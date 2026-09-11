function valueOf(object, ...keys) {
  for (const key of keys) {
    const value = object?.[key] ?? object?.[key[0]?.toUpperCase() + key.slice(1)]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return ''
}

function listOf(value) {
  if (Array.isArray(value)) return value
  if (value && typeof value === 'object') return Object.entries(value).map(([name, item]) => typeof item === 'object' ? { name, ...item } : { name, type: item })
  return []
}

function normalizeColumn(column, fallbackName = '') {
  const reference = valueOf(column, 'references', 'foreignKey', 'foreign_key', 'ref')
  return {
    name: String(valueOf(column, 'name', 'columnName', 'column_name') || fallbackName),
    type: String(valueOf(column, 'dataType', 'data_type', 'type', 'sqlType', 'sql_type') || 'Unknown'),
    primaryKey: Boolean(valueOf(column, 'isPrimaryKey', 'is_primary_key', 'primaryKey', 'primary_key', 'pk') || String(valueOf(column, 'key')).toUpperCase() === 'PRI'),
    nullable: valueOf(column, 'nullable', 'isNullable', 'is_nullable'),
    reference: reference && typeof reference === 'object' ? {
      table: String(valueOf(reference, 'table', 'tableName', 'table_name', 'referencedTable')),
      column: String(valueOf(reference, 'column', 'columnName', 'column_name', 'referencedColumn')),
    } : null,
  }
}

function normalizeRelation(relation) {
  const source = relation?.source || relation?.from || {}
  const target = relation?.target || relation?.to || {}
  return {
    id: String(valueOf(relation, 'id', 'name') || `${valueOf(relation, 'fromTable', 'from_table')}-${valueOf(relation, 'toTable', 'to_table')}`),
    fromTable: String(valueOf(relation, 'fromTable', 'from_table') || valueOf(source, 'table', 'tableName', 'table_name')),
    fromColumn: String(valueOf(relation, 'fromColumn', 'from_column') || valueOf(source, 'column', 'columnName', 'column_name')),
    toTable: String(valueOf(relation, 'toTable', 'to_table') || valueOf(target, 'table', 'tableName', 'table_name')),
    toColumn: String(valueOf(relation, 'toColumn', 'to_column') || valueOf(target, 'column', 'columnName', 'column_name')),
    cardinality: String(valueOf(relation, 'cardinality', 'relationshipType', 'relationship_type') || ''),
  }
}

export function parseSchemaDocument(document) {
  const root = document?.schema && typeof document.schema === 'object' ? document.schema : document
  const rawTables = root?.tables || root?.Tables || root?.entities || root?.Entities || root?.database?.tables || root?.database?.Tables
  const tables = listOf(rawTables).map((table, index) => {
    const rawColumns = valueOf(table, 'columns', 'Columns', 'fields', 'Fields')
    const columns = listOf(rawColumns).map((column, columnIndex) => normalizeColumn(column, typeof column === 'string' ? column : `column_${columnIndex + 1}`)).filter((column) => column.name)
    const tableName = String(valueOf(table, 'name', 'tableName', 'table_name', 'entityName') || `table_${index + 1}`)
    return { name: tableName, columns, description: String(valueOf(table, 'description') || '') }
  }).filter((table) => table.columns.length || table.name)

  const relations = listOf(root?.relationships || root?.Relationships || root?.relations || root?.Relations).map(normalizeRelation).filter((relation) => relation.fromTable && relation.toTable)
  const inferred = tables.flatMap((table) => table.columns.flatMap((column) => column.reference ? [{
    id: `${table.name}-${column.name}-${column.reference.table}-${column.reference.column}`,
    fromTable: table.name,
    fromColumn: column.name,
    toTable: column.reference.table,
    toColumn: column.reference.column,
    cardinality: 'FK',
  }] : []))
  const known = new Set(relations.map((relation) => `${relation.fromTable}.${relation.fromColumn}->${relation.toTable}.${relation.toColumn}`))
  return { tables, relationships: [...relations, ...inferred.filter((relation) => !known.has(`${relation.fromTable}.${relation.fromColumn}->${relation.toTable}.${relation.toColumn}`))] }
}
