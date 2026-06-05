'use client';

/**
 * ScenarioMonitor — 실행 중인 scenario 의 실시간 모니터 + 제어.
 *
 * - step list 표시 (각 step 의 상태: pending / running / success / failure / cancelled)
 * - 현재 step idx 강조 + feedback message stream
 * - pause / resume / next (step_by_step 모드) / cancel 버튼
 * - WebSocket scenario_* events 처리
 * - final_status pulse + duration
 */

import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { api } from '@/api/client';
import { StatusPulse } from './StatusPulse';
import { cn, formatTime } from '@/lib/utils';
import type {
  Scenario,
  ScenarioStep,
  WsEvent,
} from '@/lib/types';

interface Props {
  scenario: Scenario;
  executionId: string | null;
  mode: 'auto' | 'step_by_step';
  /** 0 = 무한 반복, >=1 = N회. 표시용 초기값(서버 이벤트로 갱신됨). */
  repeatCount?: number;
  className?: string;
}

type StepStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failure'
  | 'cancelled'
  | 'crashed';

interface MonitorState {
  phase: 'pending' | 'running' | 'paused' | 'success' | 'failure' | 'cancelled' | 'crashed';
  currentStepIdx: number | null;
  stepStatuses: Record<number, StepStatus>;
  stepDurations: Record<number, number>;
  feedbacks: Array<{ stepIdx: number; ts: string; message: string }>;
  startedAt: string | null;
  finishedAt: string | null;
  resultMessage: string;
  isPaused: boolean;
  // 반복(repeat) 진행 상황.
  currentIteration: number;
  totalIterations: number | null;   // null = 무한
  successIterations: number;
}

const initState = (totalIterations: number | null): MonitorState => ({
  phase: 'pending',
  currentStepIdx: null,
  stepStatuses: {},
  stepDurations: {},
  feedbacks: [],
  startedAt: null,
  finishedAt: null,
  resultMessage: '',
  isPaused: false,
  currentIteration: 0,
  totalIterations,
  successIterations: 0,
});

export function ScenarioMonitor({
  scenario, executionId, mode, repeatCount = 1, className,
}: Props) {
  // repeatCount 0 = 무한(null), 그 외 N회.
  const initialTotal = repeatCount <= 0 ? null : repeatCount;
  const [s, setS] = useState<MonitorState>(() => initState(initialTotal));
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  useEffect(() => {
    setS(initState(initialTotal));
  }, [executionId, initialTotal]);

  useWebSocket((ev: WsEvent) => {
    if (!executionId) return;
    const innerExecId = (ev.data as { execution_id?: string } | undefined)?.execution_id;
    if (innerExecId && innerExecId !== executionId) return;

    if (ev.type === 'execution_started') {
      // scenario 실행 시작 — 서버가 알려준 repeat_count 로 total 확정.
      const rc = ev.data.repeat_count;
      if (rc !== undefined) {
        setS((p) => ({ ...p, totalIterations: rc <= 0 ? null : rc }));
      }
    } else if (ev.type === 'scenario_iteration_started') {
      // 새 사이클 시작 — step 진행 상황을 리셋해 같은 step 을 다시 표시.
      setS((p) => ({
        ...p,
        phase: 'running',
        currentIteration: ev.data.iteration,
        totalIterations: ev.data.total,
        currentStepIdx: null,
        stepStatuses: {},
        stepDurations: {},
      }));
    } else if (ev.type === 'scenario_iteration_finished') {
      setS((p) => ({
        ...p,
        successIterations:
          ev.data.status === 'SUCCESS'
            ? p.successIterations + 1
            : p.successIterations,
      }));
    } else if (ev.type === 'scenario_step_started') {
      setS((p) => ({
        ...p,
        phase: 'running',
        startedAt: p.startedAt ?? ev.ts,
        currentStepIdx: ev.data.step_idx,
        stepStatuses: { ...p.stepStatuses, [ev.data.step_idx]: 'running' },
      }));
    } else if (ev.type === 'scenario_step_finished') {
      const status = mapStepStatus(ev.data.status);
      setS((p) => ({
        ...p,
        stepStatuses: { ...p.stepStatuses, [ev.data.step_idx]: status },
        stepDurations: { ...p.stepDurations, [ev.data.step_idx]: ev.data.duration_ms },
      }));
    } else if (ev.type === 'scenario_step_feedback') {
      setS((p) => ({
        ...p,
        feedbacks: [
          ...p.feedbacks,
          { stepIdx: ev.data.step_idx, ts: ev.ts, message: ev.data.message },
        ].slice(-50),
      }));
    } else if (ev.type === 'scenario_paused') {
      setS((p) => ({ ...p, isPaused: true, phase: 'paused' }));
    } else if (ev.type === 'scenario_resumed') {
      setS((p) => ({ ...p, isPaused: false, phase: 'running' }));
    } else if (ev.type === 'scenario_completed') {
      const phase = mapFinalStatus(ev.data.final_status);
      setS((p) => ({
        ...p,
        phase,
        finishedAt: ev.data.finished_at,
        resultMessage: ev.data.result_message,
        isPaused: false,
      }));
    } else if (ev.type === 'error') {
      setS((p) => ({
        ...p,
        phase: 'crashed',
        resultMessage: ev.data.message ?? 'error',
      }));
    }
  });

  const duration = useMemo(() => {
    if (!s.startedAt) return '—';
    const start = new Date(s.startedAt).getTime();
    const end = s.finishedAt ? new Date(s.finishedAt).getTime() : Date.now();
    return `${((end - start) / 1000).toFixed(1)}s`;
  }, [s.startedAt, s.finishedAt]);

  const isRunning = s.phase === 'running' || s.phase === 'paused';
  const completedCount = Object.values(s.stepStatuses).filter((st) =>
    ['success', 'failure', 'cancelled', 'crashed'].includes(st),
  ).length;

  async function controlAction(name: 'pause' | 'resume' | 'next' | 'cancel') {
    setActionErr(null);
    setActionBusy(name);
    try {
      if (name === 'pause') await api.scenarios.pause();
      else if (name === 'resume') await api.scenarios.resume();
      else if (name === 'next') await api.scenarios.next();
      else await api.scenarios.cancelRun();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : `${name} 실패`);
    } finally {
      setActionBusy(null);
    }
  }

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      <div className="rounded-2xl bg-surface p-5 shadow-card">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <p className="text-caption font-mono uppercase tracking-widest text-text-mute">
              Scenario Run · {mode}
            </p>
            <h2 className="mt-1 text-title text-text">{scenario.display_name}</h2>
          </div>
          <div className="text-right">
            <PhaseBadge phase={s.phase} />
            <div className="mt-1 font-mono text-caption tabular text-text-mute">
              {completedCount}/{scenario.steps.length} · {duration}
            </div>
            {(s.totalIterations === null || s.totalIterations > 1) && (
              <div className="mt-1 font-mono text-caption tabular text-accent">
                {s.totalIterations === null
                  ? `∞ 사이클 ${s.currentIteration}`
                  : `사이클 ${s.currentIteration}/${s.totalIterations}`}
                {s.successIterations > 0 && ` · 성공 ${s.successIterations}`}
              </div>
            )}
          </div>
        </div>

        {isRunning && (
          <div className="mt-4 flex flex-wrap gap-2">
            {!s.isPaused ? (
              <ControlButton onClick={() => controlAction('pause')} busy={actionBusy === 'pause'}>
                ⏸ 일시정지
              </ControlButton>
            ) : (
              <ControlButton
                onClick={() => controlAction('resume')}
                busy={actionBusy === 'resume'}
                primary
              >
                ▶ 재개
              </ControlButton>
            )}
            {mode === 'step_by_step' && s.isPaused && (
              <ControlButton onClick={() => controlAction('next')} busy={actionBusy === 'next'} primary>
                다음 step ↦
              </ControlButton>
            )}
            <ControlButton
              onClick={() => controlAction('cancel')}
              busy={actionBusy === 'cancel'}
              danger
            >
              취소
            </ControlButton>
          </div>
        )}

        {actionErr && (
          <div className="mt-3 rounded-lg bg-danger-soft p-2 text-caption text-danger">
            {actionErr}
          </div>
        )}
      </div>

      <div className="rounded-2xl bg-surface p-5 shadow-card">
        <h3 className="mb-3 text-caption font-mono uppercase tracking-widest text-text-mute">
          Steps
        </h3>
        <div className="flex flex-col gap-2">
          {scenario.steps.map((step, idx) => (
            <StepLine
              key={`${step.step_id}-${idx}`}
              idx={idx}
              step={step}
              status={s.stepStatuses[idx] ?? 'pending'}
              durationMs={s.stepDurations[idx]}
              isCurrent={s.currentStepIdx === idx}
            />
          ))}
        </div>
      </div>

      {s.feedbacks.length > 0 && (
        <div className="rounded-2xl bg-surface p-5 shadow-card">
          <h3 className="mb-3 text-caption font-mono uppercase tracking-widest text-text-mute">
            Feedback
          </h3>
          <div className="-mx-1 max-h-[200px] overflow-y-auto px-1">
            <AnimatePresence initial={false}>
              {s.feedbacks.map((f, i) => (
                <motion.div
                  key={`${f.ts}-${i}`}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="flex items-start gap-2 border-b border-border py-1.5 last:border-0"
                >
                  <span className="font-mono text-[0.75rem] text-text-mute">
                    {formatTime(f.ts)}
                  </span>
                  <span className="font-mono text-[0.75rem] text-text-mute">
                    step[{f.stepIdx}]
                  </span>
                  <span className="text-caption text-text-sub">{f.message}</span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {s.resultMessage && !isRunning && (
        <div
          className={cn(
            'rounded-xl p-3 text-caption',
            s.phase === 'success' && 'bg-success-soft text-success',
            (s.phase === 'failure' || s.phase === 'crashed') && 'bg-danger-soft text-danger',
            s.phase === 'cancelled' && 'bg-surface-elev text-text-sub',
          )}
        >
          {s.resultMessage}
        </div>
      )}
    </div>
  );
}

function PhaseBadge({ phase }: { phase: MonitorState['phase'] }) {
  const map: Record<MonitorState['phase'], { label: string; status: Parameters<typeof StatusPulse>[0]['status'] }> = {
    pending: { label: 'PENDING', status: 'idle' },
    running: { label: 'RUNNING', status: 'running' },
    paused: { label: 'PAUSED', status: 'idle' },
    success: { label: 'SUCCESS', status: 'success' },
    failure: { label: 'FAILURE', status: 'failure' },
    crashed: { label: 'CRASHED', status: 'failure' },
    cancelled: { label: 'CANCELLED', status: 'cancelled' },
  };
  const m = map[phase];
  return <StatusPulse status={m.status} label={m.label} />;
}

function StepLine({
  idx,
  step,
  status,
  durationMs,
  isCurrent,
}: {
  idx: number;
  step: ScenarioStep;
  status: StepStatus;
  durationMs: number | undefined;
  isCurrent: boolean;
}) {
  const statusPalette: Record<StepStatus, { dot: string; label: string }> = {
    pending: { dot: 'bg-text-mute/30', label: 'PENDING' },
    running: { dot: 'bg-running', label: 'RUNNING' },
    success: { dot: 'bg-success', label: 'SUCCESS' },
    failure: { dot: 'bg-danger', label: 'FAILURE' },
    cancelled: { dot: 'bg-text-sub', label: 'CANCELLED' },
    crashed: { dot: 'bg-danger', label: 'CRASHED' },
  };
  const p = statusPalette[status];

  return (
    <div
      className={cn(
        'flex items-center gap-3 rounded-xl border border-border bg-bg px-3 py-2.5 transition-colors',
        isCurrent && 'ring-1 ring-accent border-accent',
        status === 'failure' && 'bg-danger-soft/30',
        status === 'success' && 'bg-success-soft/30',
      )}
    >
      <span
        className={cn(
          'relative inline-block h-2.5 w-2.5 rounded-full',
          p.dot,
          status === 'running' && 'pulse-ring',
        )}
      />
      <span className="grid h-6 w-6 place-items-center rounded-md bg-surface-elev font-mono text-[0.6875rem] text-text-sub">
        {idx + 1}
      </span>
      <span
        className={cn(
          'rounded-full px-2 py-0.5 text-[0.6875rem] font-mono uppercase tracking-wider',
          step.kind === 'action'
            ? 'bg-accent-soft text-accent'
            : 'bg-warning-soft text-warning',
        )}
      >
        {step.kind}
      </span>
      <span className="font-mono text-caption text-text">{step.step_id}</span>
      <span className="text-caption text-text-sub">
        {step.kind === 'action' ? step.tree_id : `${step.seconds}s`}
      </span>
      <span className="ml-auto font-mono text-[0.6875rem] tabular text-text-mute">
        {durationMs != null ? `${(durationMs / 1000).toFixed(1)}s` : ''}
      </span>
      <span className="font-mono text-[0.6875rem] tabular text-text-mute">
        {p.label}
      </span>
    </div>
  );
}

function ControlButton({
  onClick,
  busy,
  primary,
  danger,
  children,
}: {
  onClick: () => void;
  busy: boolean;
  primary?: boolean;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={cn(
        'inline-flex h-9 items-center gap-2 rounded-full px-4 text-caption font-semibold',
        'transition-transform active:scale-95 disabled:opacity-50',
        primary && 'bg-accent text-white hover:bg-accent-hover',
        danger && 'bg-danger text-white hover:bg-danger-hover',
        !primary && !danger && 'bg-surface-elev text-text hover:bg-border',
      )}
    >
      {busy ? '…' : children}
    </button>
  );
}

function mapStepStatus(s: string): StepStatus {
  switch (s) {
    case 'SUCCESS':
      return 'success';
    case 'FAILURE':
      return 'failure';
    case 'CANCELLED':
      return 'cancelled';
    case 'CRASHED':
      return 'crashed';
    default:
      return 'failure';
  }
}

function mapFinalStatus(s: string): MonitorState['phase'] {
  switch (s) {
    case 'SUCCESS':
      return 'success';
    case 'FAILURE':
      return 'failure';
    case 'CANCELLED':
      return 'cancelled';
    case 'CRASHED':
      return 'crashed';
    default:
      return 'failure';
  }
}
