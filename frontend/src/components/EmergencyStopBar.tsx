'use client';

import { useState } from 'react';
import { api } from '@/api/client';
import { useWebSocket } from '@/hooks/useWebSocket';
import { StatusPulse } from './StatusPulse';
import { cn } from '@/lib/utils';
import type { ActiveExecutionInfo } from '@/lib/types';

/**
 * 운영 critical safety bar — 어디서나 1 클릭 접근.
 *
 * - 상단 고정 (sticky), 좌측 brand + 우측 E-STOP 버튼
 * - active execution 정보 표시 (tree_id + RUNNING pulse)
 * - E-STOP 클릭 → confirm dialog → /api/emergency-stop POST
 * - WebSocket welcome 의 active_execution snapshot 활용 (handoff E-3 — polling 불필요)
 */
export function EmergencyStopBar() {
  const [active, setActive] = useState<ActiveExecutionInfo | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useWebSocket((ev) => {
    if (ev.type === 'welcome') {
      setActive(ev.data.active_execution);
    } else if (ev.type === 'execution_started') {
      setActive({
        execution_id: ev.data.execution_id,
        kind: ev.data.kind,
        tree_id: ev.data.tree_id,
        scenario_id: ev.data.scenario_id,
        current_step_idx: null,
        started_at: ev.data.started_at,
      });
    } else if (
      ev.type === 'execution_finished' ||
      ev.type === 'emergency_stopped'
    ) {
      setActive(null);
    }
  });

  async function handleStop() {
    setBusy(true);
    setErr(null);
    try {
      await api.emergencyStop();
      setConfirming(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'E-STOP 실패');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="sticky top-0 z-40 w-full border-b border-border bg-bg/80 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1280px] items-center gap-4 px-6">
        <a
          href="/"
          className="flex items-center gap-2.5 text-title font-bold tracking-tight"
        >
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-text" aria-hidden />
          <span>bt_execution</span>
          <span className="text-text-mute font-normal">/</span>
          <span className="font-mono text-caption text-text-mute">v0.1</span>
        </a>

        <nav className="ml-2 hidden items-center gap-1 md:flex">
          <NavLink href="/">대시보드</NavLink>
          <NavLink href="/single">단일 실행</NavLink>
          <NavLink href="/scenarios" disabled>시나리오</NavLink>
          <NavLink href="/history" disabled>이력</NavLink>
        </nav>

        <div className="ml-auto flex items-center gap-4">
          {active ? (
            <div className="flex items-center gap-3 rounded-full bg-surface-elev px-3 py-1.5">
              <StatusPulse status="running" label="RUNNING" />
              <span className="font-mono text-caption text-text">
                {active.tree_id ?? `scenario:${active.scenario_id ?? '?'}`}
              </span>
            </div>
          ) : (
            <StatusPulse status="idle" label="대기" />
          )}

          <button
            onClick={() => setConfirming(true)}
            className={cn(
              'group relative inline-flex h-9 items-center gap-2 rounded-full px-4',
              'bg-danger text-white text-caption font-semibold tracking-wider',
              'shadow-[0_0_0_1px_rgba(240,68,82,.2),0_1px_2px_rgba(240,68,82,.4)]',
              'transition-transform hover:scale-[1.02] active:scale-[0.98]',
              active && 'animate-pulse',
            )}
            title="모든 실행을 즉시 취소"
          >
            <span className="relative inline-block h-2 w-2 rounded-sm bg-white" />
            E-STOP
          </button>
        </div>
      </div>

      {confirming && (
        <EmergencyStopConfirm
          active={active}
          busy={busy}
          error={err}
          onConfirm={handleStop}
          onCancel={() => {
            if (!busy) setConfirming(false);
          }}
        />
      )}
    </div>
  );
}

function NavLink({
  href,
  children,
  disabled,
}: {
  href: string;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  if (disabled) {
    return (
      <span className="cursor-not-allowed rounded-full px-3 py-1.5 text-caption text-text-mute">
        {children}
      </span>
    );
  }
  return (
    <a
      href={href}
      className="rounded-full px-3 py-1.5 text-caption text-text-sub transition-colors hover:bg-surface-elev hover:text-text"
    >
      {children}
    </a>
  );
}

function EmergencyStopConfirm({
  active,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  active: ActiveExecutionInfo | null;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-[420px] animate-fade-up rounded-2xl bg-surface p-6 shadow-elev">
        <div className="mb-4 flex items-start gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-danger-soft">
            <span className="inline-block h-3 w-3 rounded-sm bg-danger" />
          </div>
          <div>
            <h2 className="text-title">E-STOP</h2>
            <p className="mt-0.5 text-caption text-text-sub">
              현재 실행을 즉시 중단합니다. 작동 중인 모든 액션이 취소됩니다.
            </p>
          </div>
        </div>

        {active ? (
          <div className="mb-4 rounded-xl border border-border bg-surface-elev p-3">
            <div className="text-caption text-text-mute">실행 중</div>
            <div className="mt-0.5 flex items-center gap-2">
              <StatusPulse status="running" label="" />
              <span className="font-mono text-body text-text">
                {active.tree_id ?? `scenario:${active.scenario_id ?? '?'}`}
              </span>
            </div>
          </div>
        ) : (
          <div className="mb-4 rounded-xl border border-border bg-surface-elev p-3 text-caption text-text-sub">
            현재 실행 중인 트리가 없습니다. 그래도 모든 active goal 을 cancel 합니다.
          </div>
        )}

        {error && (
          <div className="mb-3 rounded-lg bg-danger-soft p-2 text-caption text-danger">
            {error}
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={onCancel}
            disabled={busy}
            className="flex-1 rounded-full bg-surface-elev px-4 py-2.5 text-body font-medium text-text-sub hover:bg-border disabled:opacity-50"
          >
            취소
          </button>
          <button
            onClick={onConfirm}
            disabled={busy}
            className="flex-1 rounded-full bg-danger px-4 py-2.5 text-body font-semibold text-white hover:bg-danger-hover disabled:opacity-50"
          >
            {busy ? '중단 중…' : '중단 실행'}
          </button>
        </div>
      </div>
    </div>
  );
}
