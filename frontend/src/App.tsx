import { useEffect, useState } from 'react'
import { Activity, AlertTriangle, Check, CheckCircle2, ChevronDown, CircleDashed, Clock3, GitPullRequest, LayoutList, Menu, Plus, Search, Settings2, ShieldCheck, Terminal, X } from 'lucide-react'
import './App.css'
import { fetchJobs, approveJob, rejectJob, type BackendJob } from './api'
import { DiffViewer } from './components/DiffViewer'
import { ActivityLog } from './components/ActivityLog'
import { Repositories } from './components/Repositories'
import { Settings } from './components/Settings'
import { AlertIngestModal } from './components/AlertIngestModal'

type Status = 'Review' | 'Generating' | 'Validated' | 'PR created' | 'Failed'
type Incident = {
  id: string
  rawJobId: string
  title: string
  service: string
  source: string
  status: Status
  rawStatus: string
  severity: 'High' | 'Medium' | 'Low'
  confidence: number
  age: string
  file: string
  branch: string
  summary: string
  detail: string
  unifiedDiff: string | null
}

const demoIncidents: Incident[] = [
  { id: 'ALE-1842', rawJobId: 'job-1842', title: 'Transaction fee calculation fails for tiered discounts', service: 'payments-api', source: 'Datadog', status: 'Validated', rawStatus: 'DRY_RUN_PASSED', severity: 'High', confidence: 94, age: '12 min', file: 'transaction_service.py', branch: 'fix/aletheia-ALE-1842', summary: 'Division by zero when a zero-value discount tier reaches fee calculation.', detail: 'The generated patch replaces the invalid divisor with the normalized fee multiplier used by the surrounding calculation path.', unifiedDiff: '--- transaction_service.py\n+++ transaction_service.py\n@@ -10,3 +10,3 @@\n-return total / discount_tier\n+divisor = discount_tier if discount_tier > 0 else 1.0\n+return total / divisor' },
  { id: 'ALE-1839', rawJobId: 'job-1839', title: 'Worker heartbeat missing after database reconnect', service: 'jobs-worker', source: 'Prometheus', status: 'Review', rawStatus: 'GENERATED', severity: 'High', confidence: 81, age: '28 min', file: 'worker/heartbeat.py', branch: 'fix/aletheia-ALE-1839', summary: 'Heartbeat task is not restarted after an async database connection is renewed.', detail: 'ALETHEIA found one narrow change in the reconnect handler.', unifiedDiff: '--- worker/heartbeat.py\n+++ worker/heartbeat.py\n@@ -45,2 +45,3 @@\n await db.reconnect()\n+asyncio.create_task(start_heartbeat())' },
]

function StatusIcon({ status }: { status: Status }) {
  if (status === 'Validated' || status === 'PR created') return <CheckCircle2 size={15} />
  if (status === 'Failed') return <AlertTriangle size={15} />
  if (status === 'Generating') return <CircleDashed size={15} />
  return <Clock3 size={15} />
}

function formatAge(createdAt: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(createdAt).getTime()) / 60_000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  return `${hours} hr`
}

function toIncident(job: BackendJob): Incident {
  const statusMap: Record<string, Status> = {
    PENDING: 'Review',
    GENERATING: 'Generating',
    GENERATED: 'Review',
    DRY_RUN_PASSED: 'Validated',
    PR_CREATED: 'PR created',
    FAILED: 'Failed',
  }
  const status = statusMap[job.status] ?? 'Review'
  return {
    id: job.job_id.slice(0, 8).toUpperCase(),
    rawJobId: job.job_id,
    title: job.bug_description || `${job.target_file || 'Repository'} remediation`,
    service: 'Remediation worker',
    source: 'Backend',
    status,
    rawStatus: job.status,
    severity: status === 'Failed' ? 'High' : 'Medium',
    confidence: job.confidence_score === null ? 0 : Math.round(job.confidence_score * 100),
    age: formatAge(job.created_at),
    file: job.target_file || 'No target file',
    branch: `fix/aletheia-${job.job_id.slice(0, 8)}`,
    summary: job.bug_description || 'Remediation job received from the backend.',
    detail: job.error_message || job.explanation || 'No additional detail available.',
    unifiedDiff: job.unified_diff,
  }
}

export function App() {
  const [activeNav, setActiveNav] = useState<'Incidents' | 'Review queue' | 'Repositories' | 'Activity' | 'Settings'>('Incidents')
  const [filter, setFilter] = useState<'All' | Status>('All')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Incident | null>(null)
  const [mobileNav, setMobileNav] = useState(false)
  const [liveIncidents, setLiveIncidents] = useState<Incident[]>(demoIncidents)
  const [apiState, setApiState] = useState<'loading' | 'connected' | 'offline'>('loading')
  const [showIngestModal, setShowIngestModal] = useState(false)
  const [isApproving, setIsApproving] = useState(false)
  const [isRejecting, setIsRejecting] = useState(false)

  const loadJobs = async (signal?: AbortSignal) => {
    try {
      const jobs = await fetchJobs(signal)
      const nextIncidents = jobs.map(toIncident)
      setLiveIncidents(nextIncidents)
      setSelected((current) => (current && nextIncidents.find((i) => i.id === current.id)) || nextIncidents[0] || null)
      setApiState('connected')
    } catch {
      if (!signal?.aborted) {
        setApiState('offline')
        if (liveIncidents.length === 0) setLiveIncidents(demoIncidents)
      }
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    void loadJobs(controller.signal)
    const poll = window.setInterval(() => { void loadJobs() }, 15_000)
    return () => { controller.abort(); window.clearInterval(poll) }
  }, [])

  const handleApprove = async () => {
    if (!selected) return
    setIsApproving(true)
    try {
      await approveJob(selected.rawJobId)
      await loadJobs()
    } catch (err: any) {
      alert(`Approval failed: ${err.message}`)
    } finally {
      setIsApproving(false)
    }
  }

  const handleReject = async () => {
    if (!selected) return
    setIsRejecting(true)
    try {
      await rejectJob(selected.rawJobId, 'Rejected from UI Review')
      await loadJobs()
    } catch (err: any) {
      alert(`Rejection failed: ${err.message}`)
    } finally {
      setIsRejecting(false)
    }
  }

  const visibleIncidents = liveIncidents.filter((incident) => {
    const matchesNav = activeNav === 'Review queue' ? (incident.status === 'Validated' || incident.status === 'Review') : true
    const matchesFilter = filter === 'All' || incident.status === filter
    const search = query.toLowerCase()
    return matchesNav && matchesFilter && (!search || `${incident.title} ${incident.service} ${incident.file} ${incident.id}`.toLowerCase().includes(search))
  })

  const reviewQueueCount = liveIncidents.filter((i) => i.status === 'Validated' || i.status === 'Review').length

  const navItems: Array<{ label: 'Incidents' | 'Review queue' | 'Repositories' | 'Activity' | 'Settings'; icon: any; count?: number }> = [
    { label: 'Incidents', icon: LayoutList },
    { label: 'Review queue', icon: ShieldCheck, count: reviewQueueCount },
    { label: 'Repositories', icon: GitPullRequest },
    { label: 'Activity', icon: Activity },
    { label: 'Settings', icon: Settings2 },
  ]

  return (
    <div className="app-shell">
      <aside className={`nav-rail ${mobileNav ? 'is-open' : ''}`}>
        <div className="brand-lockup">
          <span>ALETHEIA</span>
          <button className="icon-button rail-close" aria-label="Close navigation" onClick={() => setMobileNav(false)}>
            <X size={17} />
          </button>
        </div>
        <div className="rail-context">
          <span className="context-label">Workspace</span>
          <button className="workspace-switcher">Production <ChevronDown size={14} /></button>
        </div>
        <nav aria-label="Primary navigation">
          {navItems.map(({ label, icon: Icon, count }) => (
            <button
              key={label}
              className={`nav-item ${activeNav === label ? 'active' : ''}`}
              onClick={() => {
                setActiveNav(label)
                setMobileNav(false)
              }}
            >
              <Icon size={18} />
              <span>{label}</span>
              {Boolean(count) && <span className="nav-count">{count}</span>}
            </button>
          ))}
        </nav>
        <div className="rail-footer">
          <div className="system-state"><span className="state-dot" />All systems operational</div>
          <div className="user-chip">
            <span className="avatar">MC</span>
            <span><strong>Maya Chen</strong><small>On-call engineer</small></span>
            <ChevronDown size={14} />
          </div>
        </div>
      </aside>

      {mobileNav && <button className="scrim" aria-label="Close navigation" onClick={() => setMobileNav(false)} />}

      <main className="main-content">
        <header className="topbar">
          <button className="icon-button menu-button" aria-label="Open navigation" onClick={() => setMobileNav(true)}>
            <Menu size={20} />
          </button>
          <div className="breadcrumb">
            <span>Operations</span>
            <span className="slash">/</span>
            <strong>{activeNav}</strong>
          </div>
          <div className="topbar-actions">
            <button
              style={{ background: '#3A0940', color: '#FFF', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', fontWeight: 600 }}
              onClick={() => setShowIngestModal(true)}
            >
              <Plus size={15} /> Ingest Alert
            </button>
            <span className="topbar-divider" />
            <span className="env-tag">
              <span className={`state-dot ${apiState === 'offline' ? 'offline' : ''}`} />
              {apiState === 'loading' ? 'Connecting' : apiState === 'connected' ? 'Production' : 'Demo data'}
            </span>
          </div>
        </header>

        <div className="content-wrap">
          {activeNav === 'Activity' ? (
            <ActivityLog />
          ) : activeNav === 'Repositories' ? (
            <Repositories />
          ) : activeNav === 'Settings' ? (
            <Settings />
          ) : (
            <>
              <section className="page-heading">
                <div>
                  <p className="section-kicker">Friday, September 04, 2026</p>
                  <h1>{activeNav === 'Review queue' ? 'Review & Safety Queue' : 'Incident command center'}</h1>
                  <p className="heading-note">
                    {activeNav === 'Review queue' ? 'Verified dry-run patches waiting for human PR approval.' : 'A clear view of what needs attention across production.'}
                  </p>
                </div>
              </section>

              <section className="metric-strip">
                <div className="metric">
                  <span>Open incidents</span>
                  <strong>{liveIncidents.length}</strong>
                  <small className="metric-up">Live from backend</small>
                </div>
                <div className="metric">
                  <span>Awaiting review</span>
                  <strong>{liveIncidents.filter((i) => i.status === 'Review' || i.status === 'Validated').length}</strong>
                  <small>Requires your approval</small>
                </div>
                <div className="metric">
                  <span>Validated / PRs</span>
                  <strong>{liveIncidents.filter((i) => i.status === 'Validated' || i.status === 'PR created').length}</strong>
                  <small className="metric-good">Dry-run passed</small>
                </div>
                <div className="metric readiness">
                  <span>System readiness</span>
                  <strong>
                    <i className={`state-dot ${apiState === 'offline' ? 'offline' : ''}`} />
                    {apiState === 'connected' ? 'Ready' : apiState === 'loading' ? 'Connecting' : 'Offline'}
                  </strong>
                  <small>{apiState === 'offline' ? 'Showing demo data' : 'Backend jobs API'}</small>
                </div>
              </section>

              <section className="work-surface">
                <div className="surface-header">
                  <div>
                    <h2>{activeNav === 'Review queue' ? 'Pending Review Items' : 'Active incidents'}</h2>
                    <span className="result-count">{visibleIncidents.length} items</span>
                  </div>
                </div>

                <div className="table-controls">
                  <label className="search-field">
                    <Search size={17} />
                    <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search incidents, services, files..." />
                    <kbd>/</kbd>
                  </label>
                  <div className="filter-tabs" role="tablist">
                    {(['All', 'Review', 'Generating', 'Validated', 'Failed'] as const).map((item) => (
                      <button key={item} className={filter === item ? 'selected' : ''} onClick={() => setFilter(item)}>
                        {item}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="incident-table-wrap">
                  <table className="incident-table">
                    <thead>
                      <tr>
                        <th>Incident</th>
                        <th>Source</th>
                        <th>Status</th>
                        <th>Confidence</th>
                        <th>Age</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {visibleIncidents.map((incident) => (
                        <tr key={incident.id} className={selected?.id === incident.id ? 'selected-row' : ''} onClick={() => setSelected(incident)}>
                          <td>
                            <div className="incident-cell">
                              <span className={`severity-mark ${incident.severity.toLowerCase()}`} />
                              <div>
                                <strong>{incident.title}</strong>
                                <span><code>{incident.id}</code><i />{incident.service}</span>
                              </div>
                            </div>
                          </td>
                          <td>
                            <span className="source-cell">
                              <span className={`source-symbol ${incident.source.toLowerCase()}`}>{incident.source[0]}</span>
                              {incident.source}
                            </span>
                          </td>
                          <td>
                            <span className={`status-badge ${incident.status.toLowerCase().replace(' ', '-')}`}>
                              <StatusIcon status={incident.status} />
                              {incident.status}
                            </span>
                          </td>
                          <td>
                            <div className="confidence-cell">
                              <div className="confidence-track">
                                <span style={{ width: `${incident.confidence}%` }} />
                              </div>
                              <strong>{incident.confidence ? `${incident.confidence}%` : '—'}</strong>
                            </div>
                          </td>
                          <td><span className="age-cell">{incident.age}</span></td>
                          <td>
                            <button className="row-open" aria-label={`Open ${incident.id}`} onClick={(e) => { e.stopPropagation(); setSelected(incident) }}>
                              Inspect & Review
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </div>
      </main>

      {selected && activeNav !== 'Activity' && activeNav !== 'Repositories' && activeNav !== 'Settings' && (
        <aside className="detail-drawer" aria-label="Incident details" style={{ width: '550px' }}>
          <div className="drawer-header">
            <div>
              <span className="drawer-id">{selected.id}</span>
              <span className={`status-badge ${selected.status.toLowerCase().replace(' ', '-')}`}>
                <StatusIcon status={selected.status} />
                {selected.status}
              </span>
            </div>
            <button className="icon-button" aria-label="Close incident details" onClick={() => setSelected(null)}>
              <X size={18} />
            </button>
          </div>

          <div className="drawer-body" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div className="drawer-title">
              <span className={`severity-label ${selected.severity.toLowerCase()}`}>{selected.severity} severity</span>
              <h2>{selected.title}</h2>
              <p>{selected.service} <span>in</span> {selected.source}</p>
            </div>

            <div className="detail-section">
              <h3>What happened</h3>
              <p className="summary-text">{selected.summary}</p>
            </div>

            {/* Split / Unified Diff Review Box */}
            <div className="detail-section">
              <h3>Code Diff Review & Approval</h3>
              <DiffViewer
                unifiedDiff={selected.unifiedDiff}
                targetFile={selected.file}
                status={selected.rawStatus}
                onApprove={handleApprove}
                onReject={handleReject}
                isApproving={isApproving}
                isRejecting={isRejecting}
              />
            </div>

            <div className="timeline">
              <h3>Remediation Timeline</h3>
              {[
                ['Alert received', 'done', selected.age + ' ago'],
                ['Patch analysis', selected.status !== 'Generating' ? 'done' : 'current', selected.status === 'Generating' ? 'Running now' : 'Completed'],
                ['Dry-run validation', selected.status === 'Validated' || selected.status === 'PR created' ? 'done' : '', selected.status === 'Validated' || selected.status === 'PR created' ? 'Passed cleanly' : 'Waiting'],
                ['Pull request', selected.status === 'PR created' ? 'done' : '', selected.status === 'PR created' ? 'Open on GitHub' : 'Approval required'],
              ].map(([label, state, time]) => (
                <div className={`timeline-item ${state}`} key={label}>
                  <span>{state === 'done' ? <Check size={12} /> : state === 'current' ? <CircleDashed size={13} /> : <Terminal size={13} />}</span>
                  <div>
                    <strong>{label}</strong>
                    <small>{time}</small>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </aside>
      )}

      {showIngestModal && (
        <AlertIngestModal
          onClose={() => setShowIngestModal(false)}
          onIngested={() => {
            void loadJobs()
          }}
        />
      )}
    </div>
  )
}

export default App
