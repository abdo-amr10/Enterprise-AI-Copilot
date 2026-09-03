import { request } from './httpClient'

const BASE_PATH = '/api/v1/semantic-layer'

export function getSemanticLayerStatus() {
  return request(`${BASE_PATH}/status`)
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
