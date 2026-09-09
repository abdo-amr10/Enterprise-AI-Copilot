import { request, requestFile } from './httpClient'

const BASE_PATH = '/api/v1/semantic-layer'

function asArray(payload) {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.items)) return payload.items
  if (Array.isArray(payload?.data)) return payload.data
  if (payload?.data && typeof payload.data === 'object') return [payload.data]
  if (payload && typeof payload === 'object' && (payload.semanticLayerId || payload.SemanticLayerId || payload.layerId || payload.id)) return [payload]
  return []
}

function normalizeTable(table) {
  return {
    name: table?.tableName ?? table?.name ?? '',
    description: table?.description ?? '',
    columnCount: table?.columnCount ?? table?.columnsCount,
    isAllowed: Boolean(table?.isAllowed ?? table?.allowed ?? true),
  }
}

function normalizeLayer(layer) {
  return {
    id: layer?.semanticLayerId ?? layer?.SemanticLayerId ?? layer?.layerId ?? layer?.LayerId ?? layer?.id ?? layer?.Id ?? '',
    name: layer?.name ?? layer?.Name ?? 'Untitled semantic layer',
    description: layer?.description ?? layer?.Description ?? '',
    databaseName: layer?.databaseName ?? layer?.DatabaseName ?? layer?.database ?? layer?.Database ?? '',
    isActive: Boolean(layer?.isActive ?? layer?.IsActive ?? layer?.active ?? layer?.Active),
    hasApprovedRevision: Boolean(layer?.hasApprovedRevision ?? layer?.HasApprovedRevision ?? layer?.approvedRevisionId ?? layer?.ApprovedRevisionId),
    sources: normalizeSemanticSources(layer),
  }
}

function sameId(left, right) {
  return String(left || '').toLowerCase() === String(right || '').toLowerCase()
}

export function normalizeSemanticSources(payload) {
  const data = payload?.data && typeof payload.data === 'object' ? payload.data : payload
  const containers = [data?.sources, data?.sourceFiles, data?.sourceFileIds, data?.files, data?.revision, data?.currentRevision, data?.approvedRevision, data?.semanticLayer, data].filter((value) => value && typeof value === 'object')
  const sourceKeyForType = (value) => {
    const type = String(value?.fileType || value?.type || value?.sourceType || value?.kind || '').toLowerCase().replace(/[^a-z]/g, '')
    if (type.includes('schema')) return 'schemaFileId'
    if (type.includes('documentation') || type.includes('document')) return 'documentationFileId'
    if (type.includes('glossary') || type.includes('business')) return 'glossaryFileId'
    if (type.includes('sample')) return 'sampleDataFileId'
    return ''
  }
  const fromList = containers.filter(Array.isArray).flat().reduce((result, file) => {
    const key = sourceKeyForType(file)
    const id = file?.fileId ?? file?.FileId ?? file?.id ?? file?.Id
    if (key && id) result[key] = id
    return result
  }, {})
  const getValue = (sourceKey, shortKey) => {
    for (const container of containers) {
      const value = container[sourceKey] ?? container[sourceKey[0].toUpperCase() + sourceKey.slice(1)] ?? container[shortKey] ?? container[shortKey[0].toUpperCase() + shortKey.slice(1)]
      if (value !== undefined && value !== null && value !== '') {
        return typeof value === 'object' ? value.fileId ?? value.FileId ?? value.id ?? value.Id ?? '' : value
      }
    }
    return ''
  }
  return {
    schemaFileId: fromList.schemaFileId || getValue('schemaFileId', 'schema'),
    documentationFileId: fromList.documentationFileId || getValue('documentationFileId', 'documentation'),
    glossaryFileId: fromList.glossaryFileId || getValue('glossaryFileId', 'glossary'),
    sampleDataFileId: fromList.sampleDataFileId || getValue('sampleDataFileId', 'sampleData'),
  }
}

export async function getSemanticLayers() {
  const response = await request(BASE_PATH)
  return asArray(response).map(normalizeLayer).filter((layer) => layer.id)
}

export async function getSemanticLayerById(layerId) {
  let response = null
  try {
    response = await request(`${BASE_PATH}?id=${encodeURIComponent(layerId)}`)
  } catch {
    // Fall through to the collection lookup below; some deployments do not
    // implement the optional id filter consistently yet.
  }
  const layers = asArray(response).map(normalizeLayer)
  const match = layers.find((layer) => sameId(layer.id, layerId))
  if (match) return match

  // Some API deployments return an empty payload for the filtered query while
  // still exposing the layer in the unfiltered collection. Keep the lookup
  // resilient without changing the page contract.
  let allLayers
  try {
    allLayers = asArray(await request(BASE_PATH)).map(normalizeLayer)
  } catch {
    return null
  }
  return allLayers.find((layer) => sameId(layer.id, layerId)) ?? null
}

export function activateSemanticLayer(layerId) {
  return request(`${BASE_PATH}/${encodeURIComponent(layerId)}/activate`, { method: 'POST' })
}

export function deleteSemanticLayer(layerId) {
  return request(`${BASE_PATH}/${encodeURIComponent(layerId)}`, { method: 'DELETE' })
}

export function getSemanticLayerStatus(layerId) {
  const query = layerId ? `?id=${encodeURIComponent(layerId)}` : ''
  return request(`${BASE_PATH}/status${query}`).then((response) => ({ ...(response || {}), sources: normalizeSemanticSources(response) }))
}

export function getSemanticSourceFile(fileId) {
  return request(`${BASE_PATH}/files/${encodeURIComponent(fileId)}`)
}

export function getSemanticSourceFileContent(fileId) {
  return requestFile(`${BASE_PATH}/files/${encodeURIComponent(fileId)}/content`)
}

export async function getSemanticRevisionSchemaFile(semanticLayerId) {
  if (!semanticLayerId) throw new Error('This revision is not linked to a semantic layer.')
  const status = await getSemanticLayerStatus(semanticLayerId)
  const fileId = status?.sources?.schemaFileId
  if (!fileId) return { status, fileId: '', blob: null, fileName: '' }
  const file = await getSemanticSourceFileContent(fileId)
  return { ...file, status, fileId }
}

export function getSemanticRevision(revisionId) {
  return request(`${BASE_PATH}/revisions/${encodeURIComponent(revisionId)}`)
}

export function reviewSemanticRevision({ semanticLayerId, revisionId, decision, comments = '' }) {
  return request(`${BASE_PATH}/review`, {
    method: 'POST',
    body: JSON.stringify({ semanticLayerId, revisionId, decision, comments: comments.trim() || null }),
  })
}

export function getActiveSemanticRevisionSchema() {
  return request(`${BASE_PATH}/revisions/active/schema`)
}

export async function getSemanticLayerTables(layerId) {
  const response = await request(`${BASE_PATH}/${encodeURIComponent(layerId)}/tables`)
  return asArray(response?.tables ?? response).map(normalizeTable).filter((table) => table.name)
}

export async function getSemanticLayerTablePermissions(layerId) {
  const response = await request(`${BASE_PATH}/${encodeURIComponent(layerId)}/users/table-permissions`)
  const data = response?.data && typeof response.data === 'object' ? response.data : response
  const tableNames = Array.isArray(data?.tableNames) ? data.tableNames : []
  const users = Array.isArray(data?.users) ? data.users.map((user) => ({
    userId: user?.userId ?? user?.UserId ?? '',
    email: user?.email ?? user?.Email ?? '',
    displayName: user?.displayName ?? user?.DisplayName ?? `${user?.firstName ?? ''} ${user?.lastName ?? ''}`.trim(),
    tables: Object.fromEntries(tableNames.map((tableName) => [tableName, Boolean(user?.tables?.[tableName] ?? user?.Tables?.[tableName])])),
  })).filter((user) => user.userId) : []
  return { semanticLayerId: data?.semanticLayerId ?? data?.SemanticLayerId ?? layerId, tableNames, users }
}

export function setSemanticLayerTableAccess({ layerId, tableName, isAllowed }) {
  return request(`${BASE_PATH}/${encodeURIComponent(layerId)}/tables/${encodeURIComponent(tableName)}/toggle`, {
    method: 'PATCH',
    body: JSON.stringify(Boolean(isAllowed)),
  })
}

export function setUserTableAccess({ layerId, email, tableName, isAllowed }) {
  const query = new URLSearchParams({ email: email.trim(), tableName })
  return request(`${BASE_PATH}/${encodeURIComponent(layerId)}/users/table-permission?${query.toString()}`, {
    method: 'PATCH',
    body: JSON.stringify(Boolean(isAllowed)),
  })
}

export function deleteSemanticSourceFile(fileId) {
  return request(`${BASE_PATH}/files/${encodeURIComponent(fileId)}`, { method: 'DELETE' })
}

export function upsertSemanticSourceFile({ layerId, fileId, fileType, file }) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('fileType', fileType)
  const query = fileId ? `?fileId=${encodeURIComponent(fileId)}` : ''
  return request(`${BASE_PATH}/${encodeURIComponent(layerId)}/files${query}`, {
    method: 'PUT',
    body: formData,
  })
}

export function uploadSemanticSources({ name, description, files }) {
  const formData = new FormData()
  formData.append('name', name.trim())
  formData.append('description', description.trim())
  Object.entries(files).forEach(([field, file]) => {
    if (file) formData.append(field, file)
  })
  return request(`${BASE_PATH}/upload`, { method: 'POST', body: formData }).then((response) => ({ ...(response || {}), sources: normalizeSemanticSources(response) }))
}

export function generateSemanticDraft({ semanticLayerId, triggerType, sourceFileIds, baseRevisionId = null }) {
  return request(`${BASE_PATH}/generate-draft`, {
    method: 'POST',
    body: JSON.stringify({ semanticLayerId, triggerType, sourceFileIds, baseRevisionId, affectedObjects: [] }),
  })
}
