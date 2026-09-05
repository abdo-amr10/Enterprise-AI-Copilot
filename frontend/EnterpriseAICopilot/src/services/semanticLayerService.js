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

function normalizeTablePermission(permission) {
  return {
    email: permission?.email ?? permission?.userEmail ?? permission?.user?.email ?? '',
    tableName: permission?.tableName ?? permission?.table?.name ?? '',
    isAllowed: Boolean(permission?.isAllowed ?? permission?.allowed ?? false),
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
  }
}

function sameId(left, right) {
  return String(left || '').toLowerCase() === String(right || '').toLowerCase()
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
  return request(`${BASE_PATH}/status${query}`)
}

export function getSemanticSourceFile(fileId) {
  return request(`${BASE_PATH}/files/${encodeURIComponent(fileId)}`)
}

export function getSemanticSourceFileContent(fileId) {
  return requestFile(`${BASE_PATH}/files/${encodeURIComponent(fileId)}/content`)
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
  return asArray(response?.permissions ?? response).map(normalizeTablePermission).filter((permission) => permission.email && permission.tableName)
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
  return request(`${BASE_PATH}/upload`, { method: 'POST', body: formData })
}

export function generateSemanticDraft({ semanticLayerId, triggerType, sourceFileIds, baseRevisionId = null }) {
  return request(`${BASE_PATH}/generate-draft`, {
    method: 'POST',
    body: JSON.stringify({ semanticLayerId, triggerType, sourceFileIds, baseRevisionId, affectedObjects: [] }),
  })
}
