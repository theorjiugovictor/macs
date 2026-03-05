/**
 * useSwarm — WebSocket hook
 * Connects to the bulletin board WebSocket server and maintains local state.
 */

import { useState, useEffect, useRef, useCallback } from 'react'

const WS_URL = 'ws://localhost:8765'
const MAX_EVENTS = 300

export function useSwarm() {
  const [events, setEvents] = useState([])
  const [agents, setAgents] = useState({
    MEDIC:      { status: 'unknown', lastSeen: null, actionCount: 0 },
    LOGISTICS:  { status: 'unknown', lastSeen: null, actionCount: 0 },
    POWER:      { status: 'unknown', lastSeen: null, actionCount: 0 },
    COMMS:      { status: 'unknown', lastSeen: null, actionCount: 0 },
    EVAC:       { status: 'unknown', lastSeen: null, actionCount: 0 },
  })
  const [connected, setConnected] = useState(false)
  const [scenario, setScenario] = useState(null)
  const wsRef = useRef(null)

  const processEvent = useCallback((event) => {
    // Update agent state
    if (event.source !== 'SYSTEM') {
      setAgents(prev => {
        const agentId = event.source
        if (!prev[agentId]) return prev
        return {
          ...prev,
          [agentId]: {
            ...prev[agentId],
            status: event.event_type === 'AGENT_OFFLINE' ? 'offline'
                  : event.event_type === 'AGENT_ONLINE'  ? 'online'
                  : 'active',
            lastSeen: event.timestamp,
            actionCount: event.event_type === 'ACTION_TAKEN'
              ? prev[agentId].actionCount + 1
              : prev[agentId].actionCount,
          },
        }
      })
    }

    // Track scenario
    if (event.event_type === 'SCENARIO_START') {
      setScenario(event.payload?.scenario || 'unknown')
    }
  }, [])

  useEffect(() => {
    let dead = false

    function connect() {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
      }

      ws.onmessage = (msg) => {
        const data = JSON.parse(msg.data)

        if (data.type === 'history') {
          setEvents(prev => {
            const seen = new Set(prev.map(e => e.id))
            const fresh = data.events.filter(e => !seen.has(e.id))
            const merged = [...prev, ...fresh]
            return merged.slice(-MAX_EVENTS)
          })
          data.events.forEach(processEvent)
        } else {
          processEvent(data)
          setEvents(prev => {
            if (prev.some(e => e.id === data.id)) return prev
            const next = [...prev, data]
            return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next
          })
        }
      }

      ws.onclose = () => {
        setConnected(false)
        if (!dead) setTimeout(connect, 2000)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()
    return () => {
      dead = true
      if (wsRef.current) wsRef.current.close()
    }
  }, [processEvent])

  return { events, agents, connected, scenario }
}
