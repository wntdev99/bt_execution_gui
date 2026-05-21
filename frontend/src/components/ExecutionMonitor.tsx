'use client';

import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { StatusPulse } from './StatusPulse';
import { cn, formatTime } from '@/lib/utils';
import type { WsEvent } from '@/lib/types';

interface Props {
  executionId: string | null;
  className?: string;
}

type Phase = 'idle' | 'running' | 'success' | 'failure' | 'cancelled';

interface MonitorState {
  phase: Phase;
  startedAt: string | null;
  finishedAt: string | null;
  returnMessage: string;
}

/**
 * Real-time execution monitor.
 *
 * - executionId 가 set 되면 그 후의 WS event 만 필터
 * - timeline view (slide-in animation)
 * - 최종 status pulse
 */
export function ExecutionMonitor({ executionId, className }: Props) {
  const [state, setState] = useState<MonitorState>({
    phase: 'idle',
    startedAt: null,
    finishedAt: null,
    returnMessage: '',
  });
  const [feed, setFeed] = useState<WsEvent[]>([]);

  // Reset when target execution changes
  useEffect(() => {
    setFeed([]);
    setState({
      phase: executionId ? 'running' : 'idle',
      startedAt: null,
      finishedAt: null,
      returnMessage: '',
    });
  }, [executionId]);

  useWebSocket((ev) => {
    if (!executionId) return;
    const evExecId = (ev as { execution_id?: string }).execution_id;
    if (!evExecId || evExecId !== executionId) return;

    setFeed((prev) => [...prev, ev].slice(-30));

    if (ev.type === 'execution_started') {
      setState((s) => ({ ...s, phase: 'running', startedAt: ev.ts }));
    } else if (ev.type === 'execution_finished') {
      const status = ev.status === 'SUCCESS'
        ? 'success'
        : ev.status === 'CANCELLED'
          ? 'cancelled'
          : 'failure';
      setState((s) => ({
        ...s,
        phase: status,
        finishedAt: ev.ts,
        returnMessage: ev.return_message ?? '',
      }));
    } else if (ev.type === 'execution_cancelled') {
      setState((s) => ({
        ...s,
        phase: 'cancelled',
        finishedAt: ev.ts,
        returnMessage: ev.reason ?? '',
      }));
    }
  });

  const duration = useMemo(() => {
    if (!state.startedAt) return '—';
    const start = new Date(state.startedAt).getTime();
    const end = state.finishedAt
      ? new Date(state.finishedAt).getTime()
      : Date.now();
    return `${((end - start) / 1000).toFixed(1)}s`;
  }, [state.startedAt, state.finishedAt]);

  if (!executionId) {
    return (
      <div className={cn(
        'rounded-2xl border border-dashed border-border bg-surface-elev/50 p-8 text-center',
        className,
      )}>
        <p className="text-caption text-text-mute">
          실행 시 모니터가 여기 표시됩니다.
        </p>
      </div>
    );
  }

  return (
    <div className={cn('flex flex-col gap-3 rounded-2xl bg-surface p-5 shadow-card', className)}>
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex flex-col gap-1">
          <span className="text-caption text-text-mute">실행 ID</span>
          <span className="font-mono text-caption tabular text-text">{executionId.slice(0, 18)}…</span>
        </div>
        <div className="text-right">
          <StatusPulse status={state.phase} />
          <div className="mt-1 font-mono text-caption tabular text-text-mute">
            {duration}
          </div>
        </div>
      </div>

      <div className="-mx-1 max-h-[260px] overflow-y-auto px-1">
        <AnimatePresence initial={false}>
          {feed.map((ev, i) => (
            <motion.div
              key={`${ev.type}-${ev.ts}-${i}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="flex items-start gap-3 border-b border-border py-2 last:border-0"
            >
              <span className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-text-mute" />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[0.75rem] tabular text-text-mute">
                    {formatTime(ev.ts)}
                  </span>
                  <span className="font-mono text-caption text-text">{ev.type}</span>
                </div>
                {ev.type === 'execution_feedback' && (
                  <p className="mt-0.5 text-caption text-text-sub">{ev.message}</p>
                )}
                {ev.type === 'execution_finished' && (
                  <p className="mt-0.5 text-caption text-text-sub">
                    {ev.node_status} · {ev.return_message}
                  </p>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {state.returnMessage && (
        <div className={cn(
          'rounded-lg p-3 text-caption',
          state.phase === 'success' && 'bg-success-soft text-success',
          state.phase === 'failure' && 'bg-danger-soft text-danger',
          state.phase === 'cancelled' && 'bg-surface-elev text-text-sub',
        )}>
          {state.returnMessage}
        </div>
      )}
    </div>
  );
}
