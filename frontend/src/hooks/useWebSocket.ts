/**
 * WebSocket hook with exponential backoff reconnect.
 *
 * handoff E-3 박제: welcome snapshot 의 active_execution 으로 UI 상태 복원 —
 * polling 불필요.
 */
'use client';

import { useEffect, useRef, useState } from 'react';
import type { WsEvent } from '@/lib/types';

const WS_BASE =
  typeof window !== 'undefined'
    ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.hostname}:8000/api/ws`
    : '';

type Status = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed';

export interface UseWsResult {
  status: Status;
  lastEvent: WsEvent | null;
  events: WsEvent[];   // ring buffer, last 50
  clear: () => void;
}

export function useWebSocket(onEvent?: (ev: WsEvent) => void): UseWsResult {
  const [status, setStatus] = useState<Status>('idle');
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [lastEvent, setLastEvent] = useState<WsEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!WS_BASE) return;
    let stopped = false;

    function connect() {
      if (stopped) return;
      setStatus(attemptRef.current === 0 ? 'connecting' : 'reconnecting');
      const ws = new WebSocket(WS_BASE);
      wsRef.current = ws;
      ws.onopen = () => {
        setStatus('open');
        attemptRef.current = 0;
      };
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data) as WsEvent;
          setLastEvent(data);
          setEvents((prev) => {
            const next = [...prev, data];
            return next.length > 50 ? next.slice(-50) : next;
          });
          onEventRef.current?.(data);
        } catch {
          // ignore parse errors
        }
      };
      ws.onerror = () => { /* onclose 가 처리 */ };
      ws.onclose = () => {
        if (stopped) {
          setStatus('closed');
          return;
        }
        attemptRef.current += 1;
        const delay = Math.min(1000 * 2 ** Math.min(attemptRef.current, 5), 16000);
        setTimeout(connect, delay);
      };
    }
    connect();

    return () => {
      stopped = true;
      wsRef.current?.close();
    };
  }, []);

  return {
    status,
    lastEvent,
    events,
    clear: () => setEvents([]),
  };
}
