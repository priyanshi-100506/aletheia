import { useState } from 'react'
import { Check, FileCode2, Copy, ShieldAlert } from 'lucide-react'

interface DiffViewerProps {
  unifiedDiff: string | null
  targetFile: string | null
  onApprove?: () => void
  onReject?: () => void
  isApproving?: boolean
  isRejecting?: boolean
  status: string
}

export function DiffViewer({
  unifiedDiff,
  targetFile,
  onApprove,
  onReject,
  isApproving,
  isRejecting,
  status,
}: DiffViewerProps) {
  const [viewMode, setViewMode] = useState<'unified' | 'split'>('unified')
  const [copied, setCopied] = useState(false)
  const [rejectionReason, setRejectionReason] = useState('')
  const [showRejectModal, setShowRejectModal] = useState(false)

  const copyDiff = () => {
    if (unifiedDiff) {
      navigator.clipboard.writeText(unifiedDiff)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (!unifiedDiff) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', background: '#24081F', color: '#EFE3EC', borderRadius: '4px' }}>
        <p style={{ margin: 0, fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.9rem' }}>
          No patch generated for {targetFile || 'this incident'} yet.
        </p>
      </div>
    )
  }

  const lines = unifiedDiff.split('\n')
  const addedCount = lines.filter((l) => l.startsWith('+') && !l.startsWith('+++')).length
  const removedCount = lines.filter((l) => l.startsWith('-') && !l.startsWith('---')).length

  return (
    <div style={{ border: '1px solid #DED4D9', borderRadius: '6px', overflow: 'hidden', background: '#24081F' }}>
      {/* Header bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '0.6rem 1rem',
          background: '#3A0940',
          borderBottom: '1px solid #6B1F63',
          color: '#EFE3EC',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <FileCode2 size={16} style={{ color: '#FADE85' }} />
          <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.85rem', fontWeight: 600 }}>
            {targetFile || 'unified.patch'}
          </span>
          <span style={{ fontSize: '0.75rem', color: '#0E6B5C', background: '#EFE3EC', padding: '0.1rem 0.4rem', borderRadius: '3px', fontWeight: 600 }}>
            +{addedCount}
          </span>
          <span style={{ fontSize: '0.75rem', color: '#7A1F2B', background: '#EFE3EC', padding: '0.1rem 0.4rem', borderRadius: '3px', fontWeight: 600 }}>
            -{removedCount}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{ display: 'flex', background: '#24081F', borderRadius: '4px', padding: '2px', border: '1px solid #6B1F63' }}>
            <button
              onClick={() => setViewMode('unified')}
              style={{
                background: viewMode === 'unified' ? '#6B1F63' : 'transparent',
                color: '#EFE3EC',
                border: 'none',
                padding: '0.2rem 0.6rem',
                fontSize: '0.75rem',
                borderRadius: '3px',
                cursor: 'pointer',
              }}
            >
              Unified
            </button>
            <button
              onClick={() => setViewMode('split')}
              style={{
                background: viewMode === 'split' ? '#6B1F63' : 'transparent',
                color: '#EFE3EC',
                border: 'none',
                padding: '0.2rem 0.6rem',
                fontSize: '0.75rem',
                borderRadius: '3px',
                cursor: 'pointer',
              }}
            >
              Split
            </button>
          </div>
          <button
            onClick={copyDiff}
            style={{
              background: 'transparent',
              border: '1px solid #6B1F63',
              color: '#EFE3EC',
              padding: '0.3rem 0.6rem',
              borderRadius: '4px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem',
              fontSize: '0.75rem',
            }}
          >
            {copied ? <Check size={14} color="#0E6B5C" /> : <Copy size={14} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>

      {/* Warning strip if broad patch */}
      {(addedCount + removedCount > 50) && (
        <div
          style={{
            background: '#A85D14',
            color: '#FFF3C4',
            padding: '0.4rem 1rem',
            fontSize: '0.75rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <ShieldAlert size={14} />
          <span>Large patch detected ({addedCount + removedCount} lines altered). Verify dependencies carefully before approving.</span>
        </div>
      )}

      {/* Diff content view */}
      <div style={{ maxHeight: '400px', overflowY: 'auto', padding: '0.75rem', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.8rem', lineHeight: '1.4' }}>
        {lines.map((line, idx) => {
          let bg = 'transparent'
          let color = '#EFE3EC'
          if (line.startsWith('+') && !line.startsWith('+++')) {
            bg = '#0E6B5C33'
            color = '#86EFAC'
          } else if (line.startsWith('-') && !line.startsWith('---')) {
            bg = '#7A1F2B44'
            color = '#FCA5A5'
          } else if (line.startsWith('@@')) {
            bg = '#3A0940'
            color = '#FADE85'
          }

          return (
            <div key={idx} style={{ background: bg, color, padding: '0.1rem 0.5rem', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              <span style={{ userSelect: 'none', display: 'inline-block', width: '2.5rem', color: '#A79CA3', opacity: 0.6 }}>
                {idx + 1}
              </span>
              {line}
            </div>
          )
        })}
      </div>

      {/* Action footer */}
      {onApprove && (
        <div
          style={{
            padding: '0.75rem 1rem',
            background: '#3A0940',
            borderTop: '1px solid #6B1F63',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span style={{ fontSize: '0.75rem', color: '#EFE3EC' }}>
            Status: <strong>{status}</strong>
          </span>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              onClick={() => setShowRejectModal(true)}
              disabled={isRejecting || status === 'PR_CREATED' || status === 'FAILED'}
              style={{
                background: '#7A1F2B',
                color: '#FFFFFF',
                border: 'none',
                padding: '0.4rem 0.8rem',
                borderRadius: '4px',
                cursor: status === 'PR_CREATED' || status === 'FAILED' ? 'not-allowed' : 'pointer',
                opacity: status === 'PR_CREATED' || status === 'FAILED' ? 0.5 : 1,
                fontSize: '0.8rem',
                fontWeight: 600,
              }}
            >
              Reject Patch
            </button>
            <button
              onClick={onApprove}
              disabled={isApproving}
              style={{
                background: status === 'PR_CREATED' ? '#5B4F58' : '#0E6B5C',
                color: '#FFFFFF',
                border: 'none',
                padding: '0.4rem 1rem',
                borderRadius: '4px',
                cursor: isApproving ? 'wait' : 'pointer',
                fontSize: '0.8rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
              }}
            >
              {isApproving ? 'Pushing PR...' : status === 'PR_CREATED' ? 'PR Already Created' : 'Approve & Push PR'}
            </button>
          </div>
        </div>
      )}

      {/* Reject Modal */}
      {showRejectModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: '#FFFFFF', padding: '1.5rem', borderRadius: '6px', width: '400px', border: '1px solid #DED4D9' }}>
            <h3 style={{ margin: '0 0 0.5rem 0', color: '#24081F', fontFamily: 'Fraunces, serif' }}>Reject Patch</h3>
            <p style={{ fontSize: '0.85rem', color: '#5B4F58', margin: '0 0 1rem 0' }}>Provide a reason for rejecting this automated patch:</p>
            <textarea
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              placeholder="e.g., Unintended side effect on database transaction schema"
              style={{ width: '100%', height: '80px', padding: '0.5rem', borderRadius: '4px', border: '1px solid #DED4D9', marginBottom: '1rem', fontFamily: 'IBM Plex Sans, sans-serif' }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button onClick={() => setShowRejectModal(false)} style={{ background: 'transparent', border: '1px solid #DED4D9', padding: '0.4rem 0.8rem', borderRadius: '4px' }}>Cancel</button>
              <button
                onClick={() => {
                  if (onReject) onReject()
                  setShowRejectModal(false)
                }}
                style={{ background: '#7A1F2B', color: '#FFF', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 600 }}
              >
                Confirm Reject
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
