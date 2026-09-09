import { request } from './httpClient'

const DASHBOARD_PATH = '/api/v1/dashboard/metrics'

export function getDashboardMetrics() {
  return request(DASHBOARD_PATH)
}
