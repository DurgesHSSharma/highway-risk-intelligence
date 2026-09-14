/** Snapshots come back from GET /projects/{id}/snapshots already ordered by
 * reporting_month ascending (see backend/app/routers/projects.py). */
export function latestSnapshot(snapshots) {
  if (!snapshots || snapshots.length === 0) return null
  return snapshots[snapshots.length - 1]
}

export function latestNonTerminalSnapshot(snapshots) {
  if (!snapshots) return null
  for (let i = snapshots.length - 1; i >= 0; i -= 1) {
    if (!snapshots[i].is_terminal_snapshot) return snapshots[i]
  }
  return null
}

export function findSnapshot(snapshots, reportingMonth) {
  if (!snapshots) return null
  return snapshots.find((s) => s.reporting_month === reportingMonth) || null
}
