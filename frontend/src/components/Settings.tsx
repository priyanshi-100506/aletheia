import { useState } from 'react'
import { ShieldCheck, Cpu } from 'lucide-react'

export function Settings() {
  const [geminiStatus] = useState('Connected (Gemini 1.5 Pro)')
  const [githubStatus] = useState('Authenticated (Token Active)')
  const [webhookSecret, setWebhookSecret] = useState('••••••••••••••••')
  const [maxConcurrency, setMaxConcurrency] = useState(2)

  return (
    <div style={{ padding: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontFamily: 'Fraunces, serif', fontSize: '1.8rem', color: '#24081F', margin: 0 }}>
          System Settings & Policies
        </h1>
        <p style={{ color: '#5B4F58', margin: '0.2rem 0 0 0', fontSize: '0.9rem' }}>
          Configure API credentials, concurrency thresholds, and security policies.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div style={{ background: '#FFFFFF', border: '1px solid #DED4D9', borderRadius: '6px', padding: '1.5rem' }}>
          <h3 style={{ fontFamily: 'Fraunces, serif', color: '#24081F', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Cpu size={18} color="#6B1F63" /> AI Integration Settings
          </h3>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ fontSize: '0.8rem', color: '#5B4F58', display: 'block', marginBottom: '0.3rem' }}>Gemini API Model</label>
            <input value={geminiStatus} disabled style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #DED4D9', background: '#F7F4F1', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.85rem' }} />
          </div>
          <div>
            <label style={{ fontSize: '0.8rem', color: '#5B4F58', display: 'block', marginBottom: '0.3rem' }}>GitHub Connection Status</label>
            <input value={githubStatus} disabled style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #DED4D9', background: '#F7F4F1', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.85rem' }} />
          </div>
        </div>

        <div style={{ background: '#FFFFFF', border: '1px solid #DED4D9', borderRadius: '6px', padding: '1.5rem' }}>
          <h3 style={{ fontFamily: 'Fraunces, serif', color: '#24081F', margin: '0 0 1rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <ShieldCheck size={18} color="#6B1F63" /> Security & Signing
          </h3>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ fontSize: '0.8rem', color: '#5B4F58', display: 'block', marginBottom: '0.3rem' }}>Webhook Signing Secret (HMAC SHA-256)</label>
            <input value={webhookSecret} onChange={(e) => setWebhookSecret(e.target.value)} type="password" style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #DED4D9', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.85rem' }} />
          </div>
          <div>
            <label style={{ fontSize: '0.8rem', color: '#5B4F58', display: 'block', marginBottom: '0.3rem' }}>Max Remediation Concurrency Limit</label>
            <input type="number" value={maxConcurrency} onChange={(e) => setMaxConcurrency(Number(e.target.value))} style={{ width: '100%', padding: '0.5rem', borderRadius: '4px', border: '1px solid #DED4D9', fontSize: '0.85rem' }} />
          </div>
        </div>
      </div>
    </div>
  )
}
