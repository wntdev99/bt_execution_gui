'use client';

import Link from 'next/link';
import { useState, useTransition } from 'react';
import { useAsync } from '@/hooks/useApi';
import { api, ApiError } from '@/api/client';
import { ScenarioMonitor } from '@/components/ScenarioMonitor';
import { cn } from '@/lib/utils';

/**
 * `/scenarios/[id]/run` — scenario 실행 + 실시간 모니터
 *
 * - 시나리오 상세 fetch
 * - 모드 선택 (auto / step_by_step)
 * - 실행 → execution_id 받고 ScenarioMonitor 로 전환
 * - ScenarioMonitor 안에 pause/resume/next/cancel 컨트롤
 */
export default function ScenarioRunPage({ params }: { params: { id: string } }) {
  const id = decodeURIComponent(params.id);
  const { data: scenario, loading, error } = useAsync(
    () => api.scenarios.get(id),
    [id],
  );
  const [mode, setMode] = useState<'auto' | 'step_by_step'>('auto');
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [runErr, setRunErr] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function handleRun() {
    if (!scenario) return;
    setRunErr(null);
    startTransition(async () => {
      try {
        const res = await api.scenarios.run(scenario.id, mode);
        setExecutionId(res.execution_id ?? null);
      } catch (e) {
        if (e instanceof ApiError) {
          const d = e.details as { errors?: string[] } | undefined;
          if (d?.errors) {
            setRunErr(d.errors.join('\n'));
            return;
          }
          setRunErr(`${e.code ?? e.status} · ${e.message}`);
        } else {
          setRunErr(e instanceof Error ? e.message : '실행 실패');
        }
      }
    });
  }

  if (loading) return <div className="text-text-mute">로딩…</div>;
  if (error || !scenario) {
    return (
      <div className="rounded-xl border border-danger/20 bg-danger-soft p-4 text-body text-danger">
        시나리오를 찾을 수 없습니다.
        <span className="ml-1 font-mono text-caption">{String(error)}</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between gap-3">
        <div>
          <p className="text-caption font-mono uppercase tracking-widest text-text-mute">
            Run · {scenario.id}
          </p>
          <h1 className="mt-2 text-display text-text">{scenario.display_name}</h1>
        </div>
        <Link
          href={`/scenarios/${encodeURIComponent(scenario.id)}`}
          className="text-caption text-text-sub hover:text-text"
        >
          ← 편집
        </Link>
      </header>

      {!executionId && (
        <div className="rounded-2xl bg-surface p-5 shadow-card">
          <h3 className="text-title">실행 모드</h3>
          <p className="mt-1 text-caption text-text-sub">
            <strong className="text-text">auto</strong>: 모든 step 연속 실행 / <strong className="text-text">step_by_step</strong>: 매 step 사이 자동 정지 → 다음 step 수동 진행.
          </p>

          <div className="mt-4 flex gap-2">
            <ModeChip selected={mode === 'auto'} onClick={() => setMode('auto')}>
              자동
            </ModeChip>
            <ModeChip
              selected={mode === 'step_by_step'}
              onClick={() => setMode('step_by_step')}
            >
              Step-by-step
            </ModeChip>
          </div>

          {runErr && (
            <div className="mt-3 whitespace-pre-line rounded-lg bg-danger-soft p-3 text-caption text-danger">
              {runErr}
            </div>
          )}

          <div className="mt-5">
            <button
              onClick={handleRun}
              disabled={pending}
              className="inline-flex h-11 items-center gap-2 rounded-full bg-accent px-6 text-body font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {pending ? '시작 중…' : '▶ 실행'}
            </button>
            <p className="mt-2 text-caption text-text-mute">
              실행 중에는 다른 트리/시나리오를 동시에 실행할 수 없습니다 (단일 액션 통로).
            </p>
          </div>
        </div>
      )}

      {/* Monitor 는 항상 mount — executionId=null 일 때 idle UI 로 WebSocket
         connection 미리 활성화. 사용자 ▶ 클릭 → execution_id set 시점에 monitor
         가 이미 WS 구독 중이라 첫 scenario_step_started 누락 회피 (Bug #6 fix). */}
      <ScenarioMonitor
        scenario={scenario}
        executionId={executionId}
        mode={mode}
      />
    </div>
  );
}

function ModeChip({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'h-10 rounded-full px-4 text-body font-medium transition-colors',
        selected
          ? 'bg-text text-bg'
          : 'bg-surface-elev text-text-sub hover:bg-border',
      )}
    >
      {children}
    </button>
  );
}
