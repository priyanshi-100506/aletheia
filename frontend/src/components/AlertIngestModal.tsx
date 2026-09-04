import { useState } from 'react'
import { X, Send } from 'lucide-react'
import { ingestAlert } from '../api'

interface AlertIngestModalProps {
  onClose: () => void
  onIngested: (jobId: string) => void
}

export function AlertIngestModal({ onClose, onIngested }: AlertIngestModalProps) {
  const [errorLog, setErrorLog] = useState('')
  const [targetFile, setTargetFile] = useState('transaction_service.py')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!errorLog.trim()) return

    setLoading(true)
    setError(null)

    try {
      const res = await ingestAlert(errorLog, targetFile)
      onIngested(res.job_id)
      onClose()
    } catch (err: any) {
      setError(err.message || 'Failed to ingest alert payload')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: '#FFFFFF', borderRadius: '6px', width: '550px', border: '1px solid #DED4D9', overflow: 'hidden' }}>
        <div style={{ padding: '1rem 1.5rem', background: '#24081F', color: '#FFFFFF', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontFamily: 'Fraunces, serif', fontSize: '1.2rem' }}>Simulate / Ingest Alert Payload</h3>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: '#EFE3EC', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ padding: '1.5rem' }}>
          {error && (
            <div style={{ background: '#7A1F2B', color: '#FFFFFF', padding: '0.5rem 1rem', borderRadius: '4px', marginBottom: '1rem', fontSize: '0.85rem' }}>
              {error}
            </div>
          )}

          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.8rem', color: '#5B4F58', marginBottom: '0.3rem', fontWeight: 600 }}>
              Target File Path
            </label>
            <input
              value={targetFile}
              onChange={(e) => setTargetFile(e.target.value)}
              placeholder="e.g. transaction_service.py"
              style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #DED4D9', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.85rem' }}
            />
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', fontSize: '0.8rem', color: '#5B4F58', marginBottom: '0.3rem', fontWeight: 600 }}>
              Error Trace / Incident Payload
            </label>
            <textarea
              value={errorLog}
              onChange={(e) => setErrorLog(e.target.value)}
              placeholder="Paste exception traceback or alert log here..."
              rows={6}
              required
              style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #DED4D9', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.8rem' }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button type="button" onClick={onClose} style={{ background: 'transparent', border: '1px solid #DED4D9', padding: '0.5rem 1rem', borderRadius: '4px', cursor: 'pointer' }}>
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              style={{
                background: '#3A0940',
                color: '#FFFFFF',
                border: 'none',
                padding: '0.5rem 1.2rem',
                borderRadius: '4px',
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
              }}
            >
              <Send size={15} />
              {loading ? 'Ingesting...' : 'Ingest & Trigger Remediation'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
