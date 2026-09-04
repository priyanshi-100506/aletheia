export type BackendJob = {
  job_id: string
  status: string
  target_file: string | null
  error_message: string | null
  bug_description: string | null
  explanation: string | null
  unified_diff: string | null
  confidence_score: number | null
  created_at: string
  updated_at: string
}

export type AuditLogEntry = {
  id: string
  job_id: string | null
  event_type: string
  actor: string
  details: Record<string, any> | null
  created_at: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8001/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('Accept', 'application/json')
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!response.ok) throw new Error(`API request failed: ${response.status}`)
  return response.json() as Promise<T>
}

export function fetchJobs(signal?: AbortSignal) {
  return request<BackendJob[]>('/jobs?limit=50', { signal })
}

export function fetchJob(jobId: string, signal?: AbortSignal) {
  return request<BackendJob>(`/jobs/${encodeURIComponent(jobId)}`, { signal })
}

export function ingestAlert(errorLog: string, targetFile?: string) {
  return request<{ status: string; job_id: string }>('/webhooks/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ error_log: errorLog, target_file: targetFile || undefined }),
  })
}

export function approveJob(jobId: string, actor = 'on_call_engineer') {
  return request<{ status: string; job_id: string; pull_request: any }>(`/jobs/${encodeURIComponent(jobId)}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor }),
  })
}

export function rejectJob(jobId: string, reason: string, actor = 'on_call_engineer') {
  return request<{ status: string; job_id: string }>(`/jobs/${encodeURIComponent(jobId)}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason, actor }),
  })
}

export function fetchActivity(signal?: AbortSignal) {
  return request<AuditLogEntry[]>('/activity?limit=50', { signal })
}
