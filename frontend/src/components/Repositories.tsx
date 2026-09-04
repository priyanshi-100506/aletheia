import { useState } from 'react'
import { GitBranch } from 'lucide-react'

export function Repositories() {
  const [repoInfo] = useState({
    name: 'aletheia-app/core-service',
    url: 'https://github.com/aletheia-app/core-service',
    defaultBranch: 'main',
    status: 'Healthy',
    lastSync: '2 minutes ago',
    activeWorktrees: 2,
    openPRs: 3,
    allowedPaths: ['app/', 'services/', 'transaction_service.py'],
    maxDiffSizeKB: 500,
  })

  return (
    <div style={{ padding: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontFamily: 'Fraunces, serif', fontSize: '1.8rem', color: '#24081F', margin: 0 }}>
          Configured Repositories
        </h1>
        <p style={{ color: '#5B4F58', margin: '0.2rem 0 0 0', fontSize: '0.9rem' }}>
          Repository connections, Git isolation worktrees, and safety boundaries.
        </p>
      </div>

      <div style={{ background: '#FFFFFF', border: '1px solid #DED4D9', borderRadius: '6px', padding: '1.5rem', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <GitBranch size={20} style={{ color: '#6B1F63' }} />
            <div>
              <h3 style={{ margin: 0, fontFamily: 'Fraunces, serif', color: '#24081F' }}>{repoInfo.name}</h3>
              <a href={repoInfo.url} target="_blank" rel="noreferrer" style={{ fontSize: '0.8rem', color: '#35507A' }}>
                {repoInfo.url}
              </a>
            </div>
          </div>
          <span style={{ background: '#0E6B5C', color: '#FFF', padding: '0.3rem 0.6rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600 }}>
            {repoInfo.status}
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', background: '#F7F4F1', padding: '1rem', borderRadius: '4px' }}>
          <div>
            <span style={{ fontSize: '0.75rem', color: '#5B4F58', display: 'block' }}>Default Branch</span>
            <strong style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.85rem' }}>{repoInfo.defaultBranch}</strong>
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: '#5B4F58', display: 'block' }}>Active Worktrees</span>
            <strong style={{ fontSize: '0.85rem' }}>{repoInfo.activeWorktrees} detached</strong>
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: '#5B4F58', display: 'block' }}>Open ALETHEIA PRs</span>
            <strong style={{ fontSize: '0.85rem' }}>{repoInfo.openPRs} PRs</strong>
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: '#5B4F58', display: 'block' }}>Last Sync</span>
            <strong style={{ fontSize: '0.85rem' }}>{repoInfo.lastSync}</strong>
          </div>
        </div>
      </div>
    </div>
  )
}
