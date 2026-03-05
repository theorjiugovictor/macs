import React, { useMemo, useRef, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { useSwarm } from './useSwarm'

// ── Constants ────────────────────────────────────────────────────────────────

const DOMAIN_COLOR = {
  MEDICAL:    '#f43f5e',
  LOGISTICS:  '#f97316',
  POWER:      '#eab308',
  COMMS:      '#8b5cf6',
  EVACUATION: '#06b6d4',
  SYSTEM:     '#64748b',
}

const SEVERITY_COLOR = {
  CRITICAL: '#ef4444',
  HIGH:     '#f59e0b',
  MEDIUM:   '#06b6d4',
  LOW:      '#22c55e',
  INFO:     '#4b5563',
}

const DOMAIN_ICON = {
  MEDICAL:    '🏥',
  LOGISTICS:  '🚛',
  POWER:      '⚡',
  COMMS:      '📡',
  EVACUATION: '🚌',
  SYSTEM:     '🌐',
}

const FIELD_REPORT_COLOR = '#4ade80'

const AGENT_IDS = ['MEDIC', 'LOGISTICS', 'POWER', 'COMMS', 'EVAC']

// ── Sub-components ────────────────────────────────────────────────────────────

function ConnectionBadge({ connected }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '2px 10px', borderRadius: 9999,
      fontSize: 11,
      background: connected ? '#052e16' : '#1c1017',
      color: connected ? '#4ade80' : '#f87171',
      border: `1px solid ${connected ? '#166534' : '#7f1d1d'}`,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%',
        background: connected ? '#4ade80' : '#f87171',
        boxShadow: connected ? '0 0 6px #4ade80' : 'none',
      }} />
      {connected ? 'MACS LIVE' : 'DISCONNECTED'}
    </span>
  )
}

function AgentCard({ id, data }) {
  const domain = id === 'EVAC' ? 'EVACUATION' : id === 'MEDIC' ? 'MEDICAL' : id
  const color = DOMAIN_COLOR[domain] || '#64748b'
  const icon = DOMAIN_ICON[domain] || '●'

  const statusColor =
    data.status === 'active'  ? '#4ade80' :
    data.status === 'online'  ? '#60a5fa' :
    data.status === 'offline' ? '#ef4444' : '#6b7280'

  const lastSeen = data.lastSeen
    ? new Date(data.lastSeen * 1000).toLocaleTimeString()
    : '—'

  return (
    <div style={{
      background: '#111827',
      border: `1px solid ${data.status === 'offline' ? '#7f1d1d' : color}22`,
      borderLeft: `3px solid ${color}`,
      borderRadius: 6,
      padding: '10px 14px',
      opacity: data.status === 'offline' ? 0.5 : 1,
      transition: 'opacity 0.3s',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 700, color }}>
          {icon} {id}
        </span>
        <span style={{
          fontSize: 10, padding: '1px 7px', borderRadius: 9999,
          background: `${statusColor}22`, color: statusColor,
          border: `1px solid ${statusColor}44`,
          textTransform: 'uppercase',
        }}>
          {data.status === 'unknown' ? 'waiting' : data.status}
        </span>
      </div>
      <div style={{ marginTop: 6, display: 'flex', gap: 16, color: '#6b7280', fontSize: 11 }}>
        <span>Actions: <strong style={{ color: '#e5e7eb' }}>{data.actionCount}</strong></span>
        <span>Last: <strong style={{ color: '#e5e7eb' }}>{lastSeen}</strong></span>
      </div>
    </div>
  )
}

function EventRow({ event }) {
  const color = SEVERITY_COLOR[event.severity] || '#6b7280'
  const isFieldReport = event.source === 'FIELD_REPORT'
  const domainColor = isFieldReport ? FIELD_REPORT_COLOR : (DOMAIN_COLOR[event.domain] || '#64748b')
  const icon = isFieldReport ? '📱' : (DOMAIN_ICON[event.domain] || '●')
  const isAction = event.event_type === 'ACTION_TAKEN'
  const isSystem = event.source === 'SYSTEM'
  const isCritical = event.severity === 'CRITICAL'

  const ts = new Date(event.timestamp * 1000).toLocaleTimeString()
  const msg = event.payload?.message || ''

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '70px 80px 110px 1fr',
      gap: 8,
      padding: '5px 10px',
      borderBottom: '1px solid #1f2937',
      background: isCritical ? '#1c0a0a' : isFieldReport ? '#0a1a0f' : isAction ? '#0f1922' : 'transparent',
      borderLeft: isFieldReport ? `2px solid ${FIELD_REPORT_COLOR}` : 'none',
      animation: 'fadeIn 0.3s ease',
    }}>
      <span style={{ color: '#4b5563', fontSize: 11 }}>{ts}</span>
      <span style={{
        color: domainColor,
        fontWeight: 600,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {icon} {isFieldReport ? 'CITIZEN' : event.source}
      </span>
      <span style={{
        fontSize: 10,
        padding: '1px 6px',
        borderRadius: 3,
        background: `${color}22`,
        color,
        alignSelf: 'center',
        textAlign: 'center',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {event.severity}
      </span>
      <span style={{
        color: isFieldReport ? '#86efac' : isSystem ? '#f59e0b' : isAction ? '#e5e7eb' : '#9ca3af',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {msg || event.event_type}
      </span>
    </div>
  )
}

function EmergenceGraph({ events }) {
  // Show domain activity over time (last 20 action events)
  const actionEvents = useMemo(
    () => events.filter(e => e.event_type === 'ACTION_TAKEN').slice(-20),
    [events]
  )

  const data = useMemo(() => {
    const counts = {}
    actionEvents.forEach(e => {
      counts[e.domain] = (counts[e.domain] || 0) + 1
    })
    return Object.entries(counts).map(([domain, count]) => ({ domain, count }))
  }, [actionEvents])

  if (data.length === 0) {
    return (
      <div style={{ color: '#4b5563', textAlign: 'center', padding: 20, fontSize: 12 }}>
        Waiting for agent actions...
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={120}>
      <BarChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
        <XAxis dataKey="domain" tick={{ fill: '#6b7280', fontSize: 10 }} />
        <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
        <Tooltip
          contentStyle={{ background: '#111827', border: '1px solid #1f2937', fontSize: 11 }}
          labelStyle={{ color: '#e5e7eb' }}
        />
        <Bar dataKey="count" radius={[3, 3, 0, 0]}>
          {data.map((entry) => (
            <Cell key={entry.domain} fill={DOMAIN_COLOR[entry.domain] || '#64748b'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const { events, agents, connected, scenario } = useSwarm()
  const feedRef = useRef(null)

  // Auto-scroll feed to bottom
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight
    }
  }, [events])

  const stats = useMemo(() => {
    const byDomain = {}
    const bySeverity = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 }
    let fieldReports = 0
    events.forEach(e => {
      byDomain[e.domain] = (byDomain[e.domain] || 0) + 1
      if (e.severity in bySeverity) bySeverity[e.severity]++
      if (e.source === 'FIELD_REPORT') fieldReports++
    })
    return { byDomain, bySeverity, total: events.length, fieldReports }
  }, [events])

  const criticalCount = stats.bySeverity.CRITICAL

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {/* Header */}
      <header style={{
        padding: '10px 20px',
        borderBottom: '1px solid #1f2937',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: '#0d1117',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.5px', color: '#e5e7eb' }}>
            ⬡ MACS
          </span>
          {scenario && (
            <span style={{ color: '#f59e0b', fontSize: 11 }}>
              ▸ {scenario.toUpperCase()}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          {criticalCount > 0 && (
            <span style={{
              color: '#ef4444', fontSize: 11, fontWeight: 700,
              animation: 'pulse 1s infinite',
            }}>
              ⚠ {criticalCount} CRITICAL
            </span>
          )}
          <span style={{ color: '#6b7280', fontSize: 11 }}>
            {stats.total} events
          </span>
          <ConnectionBadge connected={connected} />
        </div>
      </header>

      {/* Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left sidebar — Agents */}
        <aside style={{
          width: 220,
          flexShrink: 0,
          borderRight: '1px solid #1f2937',
          padding: 12,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          overflowY: 'auto',
          background: '#0d1117',
        }}>
          <div style={{ color: '#6b7280', fontSize: 10, marginBottom: 4, letterSpacing: 1 }}>
            MAC NODES
          </div>
          {AGENT_IDS.map(id => (
            <AgentCard key={id} id={id} data={agents[id]} />
          ))}

          {/* Severity summary */}
          <div style={{ marginTop: 16 }}>
            <div style={{ color: '#6b7280', fontSize: 10, marginBottom: 8, letterSpacing: 1 }}>
              SEVERITY
            </div>
            {Object.entries(stats.bySeverity).map(([sev, count]) => (
              <div key={sev} style={{
                display: 'flex', justifyContent: 'space-between',
                marginBottom: 4, fontSize: 11,
              }}>
                <span style={{ color: SEVERITY_COLOR[sev] }}>{sev}</span>
                <span style={{ color: '#9ca3af' }}>{count}</span>
              </div>
            ))}
          </div>

          {/* Field reports */}
          {stats.fieldReports > 0 && (
            <div style={{
              marginTop: 16,
              padding: '8px 10px',
              background: '#0a1a0f',
              border: `1px solid ${FIELD_REPORT_COLOR}33`,
              borderRadius: 6,
            }}>
              <div style={{ color: '#6b7280', fontSize: 10, marginBottom: 4, letterSpacing: 1 }}>
                FIELD INTEL
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                <span style={{ color: FIELD_REPORT_COLOR }}>📱 Citizen Reports</span>
                <span style={{ color: '#9ca3af' }}>{stats.fieldReports}</span>
              </div>
            </div>
          )}
        </aside>

        {/* Main — Event Feed */}
        <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Feed header */}
          <div style={{
            padding: '6px 10px',
            borderBottom: '1px solid #1f2937',
            display: 'flex',
            gap: 16,
            background: '#0d1117',
            flexShrink: 0,
          }}>
            <span style={{ color: '#6b7280', fontSize: 10, letterSpacing: 1 }}>
              BULLETIN BOARD — LIVE FEED
            </span>
            {Object.entries(stats.byDomain).map(([d, c]) => (
              <span key={d} style={{ fontSize: 10, color: DOMAIN_COLOR[d] || '#6b7280' }}>
                {DOMAIN_ICON[d]} {c}
              </span>
            ))}
          </div>

          {/* Scrollable feed */}
          <div ref={feedRef} style={{ flex: 1, overflowY: 'auto' }}>
            {events.length === 0 ? (
              <div style={{
                color: '#4b5563', textAlign: 'center',
                padding: 40, fontSize: 13,
              }}>
                {connected
                  ? '⬡ Waiting for MACS activity...'
                  : '⬡ Connecting to MACS...'}
              </div>
            ) : (
              events.map(event => <EventRow key={event.id} event={event} />)
            )}
          </div>
        </main>

        {/* Right sidebar — Emergence graph */}
        <aside style={{
          width: 220,
          flexShrink: 0,
          borderLeft: '1px solid #1f2937',
          padding: 12,
          background: '#0d1117',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}>
          <div style={{ color: '#6b7280', fontSize: 10, letterSpacing: 1 }}>
            EMERGENCE GRAPH
          </div>
          <EmergenceGraph events={events} />

          <div style={{ color: '#6b7280', fontSize: 10, letterSpacing: 1, marginTop: 8 }}>
            RECENT ACTIONS
          </div>
          <div style={{ fontSize: 11, display: 'flex', flexDirection: 'column', gap: 6, overflowY: 'auto' }}>
            {events
              .filter(e => e.event_type === 'ACTION_TAKEN')
              .slice(-8)
              .reverse()
              .map(e => (
                <div key={e.id} style={{
                  padding: '5px 8px',
                  borderLeft: `2px solid ${DOMAIN_COLOR[e.domain] || '#6b7280'}`,
                  background: '#111827',
                  borderRadius: '0 4px 4px 0',
                }}>
                  <div style={{ color: DOMAIN_COLOR[e.domain], fontSize: 10, fontWeight: 600 }}>
                    {e.source}
                  </div>
                  <div style={{ color: '#9ca3af', marginTop: 2, lineHeight: 1.3 }}>
                    {(e.payload?.message || '').slice(0, 80)}
                  </div>
                </div>
              ))}
          </div>
        </aside>
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity: 0; transform: translateY(-2px); } to { opacity: 1; transform: none; } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
    </div>
  )
}
