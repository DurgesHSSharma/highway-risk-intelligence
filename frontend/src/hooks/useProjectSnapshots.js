import { useApi } from './useApi'
import { listProjectSnapshots } from '../api/endpoints'

export function useProjectSnapshots(projectId) {
  return useApi((signal) => listProjectSnapshots(projectId, signal), [projectId])
}
