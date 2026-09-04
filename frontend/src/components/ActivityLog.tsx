import { useEffect, useState } from 'react'
import { fetchActivity, type AuditLogEntry } from '../api'


export function ActivityLog() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchActivity()
        setLogs(data)
      } catch (err) {
        console.error('Failed to fetch activity log', err)
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [])

  return (
    <div style={{ padding: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontFamily: 'Fraunces, serif', fontSize: '1.8rem', color: '#24081F', margin: 0 }}>
            Audit Activity Trail
          </h1>
          <p style={{ color: '#5B4F58', margin: '0.2rem 0 0 0', fontSize: '0.9rem' }}>
            Complete historical audit record of alerts, generated patches, approvals, and security events.
          </p>
        </div>
      </div>

      <div style={{ background: '#FFFFFF', border: '1px solid #DED4D9', borderRadius: '6px', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
          <thead>
            <tr style={{ background: '#F7F4F1', borderBottom: '1px solid #DED4D9', color: '#5B4F58' }}>
              <th style={{ padding: '0.75rem 1rem' }}>Timestamp</th>
              <th style={{ padding: '0.75rem 1rem' }}>Event Type</th>
              <th style={{ padding: '0.75rem 1rem' }}>Actor</th>
              <th style={{ padding: '0.75rem 1rem' }}>Job ID</th>
              <th style={{ padding: '0.75rem 1rem' }}>Details</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: '#5B4F58' }}>
                  Loading activity logs...
                </td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: '#5B4F58' }}>
                  No audit logs recorded yet. Submit webhooks or run remediations to populate.
                </td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id} style={{ borderBottom: '1px solid #EFE3EC' }}>
                  <td style={{ padding: '0.75rem 1rem', fontFamily: 'IBM Plex Mono, monospace', color: '#5B4F58' }}>
                    {new Date(log.created_at).toLocaleTimeString()}
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <span
                      style={{
                        padding: '0.2rem 0.5rem',
                        borderRadius: '3px',
                        fontWeight: 600,
                        fontSize: '0.75rem',
                        background: log.event_type.includes('FAILED')
                          ? '#7A1F2B'
                          : log.event_type.includes('GRANTED') || log.event_type.includes('PASSED')
                          ? '#0E6B5C'
                          : '#3A0940',
                        color: '#FFFFFF',
                      }}
                    >
                      {log.event_type}
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem 1rem', fontWeight: 600, color: '#24081F' }}>{log.actor}</td>
                  <td style={{ padding: '0.75rem 1rem', fontFamily: 'IBM Plex Mono, monospace', color: '#6B1F63' }}>
                    {log.job_id ? log.job_id.slice(0, 8) : '—'}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.75rem', color: '#5B4F58' }}>
                    {log.details ? JSON.stringify(log.details) : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
