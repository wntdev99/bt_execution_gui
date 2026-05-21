'use client';

import Link from 'next/link';
import { useMemo } from 'react';
import { useAsync } from '@/hooks/useApi';
import { api } from '@/api/client';
import { TreeIcon } from '@/components/TreeIcon';
import { cn, formatTime } from '@/lib/utils';
import type { HistoryDetail, HistoryStep } from '@/lib/types';

/**
 * `/history/[id]` — 실행 이력 상세
 *
 * - kind=single: payload + result_message + final_status
 * - kind=scenario: step timeline + snapshot (completed_steps/remaining_steps/failed_step_idx)
 */
export default function HistoryDetailPage({ params }: { params: { id: string } }) {
  const id = Number(decodeURIComponent(params.id));
  const { data, loading, error } = useAsync(() => api.history.get(id), [id]);

  if (Number.isNaN(id)) {
    return (
      <div className="rounded-xl border border-danger/20 bg-danger-soft p-4 text-body text-danger">
        잘못된 이력 ID 입니다.
      </div>
    );
  }
  if (loading) return <div className="text-text-mute">로딩…</div>;
  if (error || !data) {
    return (
      <div className="rounded-xl border border-danger/20 bg-danger-soft p-4 text-body text-danger">
        이력을 찾을 수 없습니다.{' '}
        <span className="font-mono text-caption">({String(error)})</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link
          href="/history"
          className="text-caption text-text-sub hover:text-text"
        >
          ← 이력 목록
        </Link>
        <p className="mt-3 text-caption font-mono uppercase tracking-widest text-text-mute">
          Execution #{data.id} · {data.kind}
        </p>
        <h1 className="mt-2 flex items-center gap-3 text-display text-text">
          {data.tree_id && (
            <span className="text-text-sub">
              <TreeIcon treeId={data.tree_id} size={36} />
            </span>
          )}
          {data.tree_id ?? data.scenario_id ?? '(unknown)'}
        </h1>
        <div className="mt-2 flex flex-wrap gap-4 text-caption">
          <Meta label="시작" value={formatTime(data.started_at)} />
          <Meta label="종료" value={formatTime(data.finished_at)} />
          <Meta label="소요" value={formatDuration(data)} />
          <FinalStatusBadge status={data.final_status ?? 'UNKNOWN'} />
        </div>
      </header>

      {data.result_message && (
        <div
          className={cn(
            'rounded-2xl p-4 text-caption',
            data.final_status === 'SUCCESS' && 'bg-success-soft text-success',
            (data.final_status === 'FAILURE' || data.final_status === 'CRASHED') &&
              'bg-danger-soft text-danger',
            data.final_status === 'CANCELLED' && 'bg-surface-elev text-text-sub',
          )}
        >
          <div className="mb-1 font-mono text-[0.6875rem] uppercase tracking-wider">
            결과 메시지
          </div>
          <div className="whitespace-pre-line">{data.result_message}</div>
        </div>
      )}

      {/* Payload (single 시 단일 payload, scenario 시 비어있을 수 있음) */}
      {data.kind === 'single' && data.payload && (
        <Section title="입력 Payload">
          <PayloadPretty payload={data.payload} />
        </Section>
      )}

      {data.kind === 'scenario' && data.steps && data.steps.length > 0 && (
        <Section title={`Step 이력 (${data.steps.length})`}>
          <div className="flex flex-col gap-2">
            {data.steps.map((step) => (
              <StepCard key={step.id} step={step} />
            ))}
          </div>
        </Section>
      )}

      {data.snapshot && Object.keys(data.snapshot).length > 0 && (
        <Section title="실행 스냅샷">
          <pre className="overflow-x-auto rounded-xl bg-surface-elev p-3 font-mono text-[0.75rem] leading-relaxed text-text-sub">
            {JSON.stringify(data.snapshot, null, 2)}
          </pre>
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl bg-surface p-5 shadow-card">
      <h3 className="mb-3 text-caption font-mono uppercase tracking-widest text-text-mute">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1">
      <span className="text-[0.6875rem] uppercase tracking-wider text-text-mute">
        {label}
      </span>
      <span className="font-mono tabular text-text">{value}</span>
    </span>
  );
}

function FinalStatusBadge({ status }: { status: string }) {
  const upper = status.toUpperCase();
  const palette: Record<string, string> = {
    SUCCESS: 'bg-success-soft text-success',
    FAILURE: 'bg-danger-soft text-danger',
    CANCELLED: 'bg-surface-elev text-text-sub',
    CRASHED: 'bg-danger-soft text-danger',
  };
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 font-mono text-[0.6875rem] tracking-wider',
        palette[upper] ?? 'bg-surface-elev text-text-mute',
      )}
    >
      {upper}
    </span>
  );
}

function StepCard({ step }: { step: HistoryStep }) {
  const duration = useMemo(() => {
    if (!step.finished_at) return null;
    const start = new Date(step.started_at).getTime();
    const end = new Date(step.finished_at).getTime();
    if (Number.isNaN(start) || Number.isNaN(end)) return null;
    return (end - start) / 1000;
  }, [step.started_at, step.finished_at]);

  const upper = (step.status ?? 'UNKNOWN').toUpperCase();
  const isSuccess = upper === 'SUCCESS';
  const isFail = upper === 'FAILURE' || upper === 'CRASHED';

  return (
    <details
      className={cn(
        'rounded-xl border border-border bg-bg p-3 open:bg-surface-elev/40',
        isSuccess && 'border-success/30',
        isFail && 'border-danger/30',
      )}
    >
      <summary className="cursor-pointer">
        <div className="inline-flex items-center gap-3">
          <span className="grid h-6 w-6 place-items-center rounded-md bg-surface-elev font-mono text-[0.6875rem] text-text-sub">
            {step.step_idx + 1}
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
          {step.tree_id && (
            <span className="font-mono text-caption text-text-sub">{step.tree_id}</span>
          )}
          <span className="ml-2 font-mono text-[0.6875rem] tabular text-text-mute">
            {duration != null ? `${duration.toFixed(1)}s` : '—'}
          </span>
          <span
            className={cn(
              'ml-auto rounded-full px-2 py-0.5 font-mono text-[0.6875rem] tracking-wider',
              isSuccess && 'bg-success-soft text-success',
              isFail && 'bg-danger-soft text-danger',
              !isSuccess && !isFail && 'bg-surface-elev text-text-sub',
            )}
          >
            {upper}
          </span>
        </div>
      </summary>

      {step.result_message && (
        <div className="mt-3 rounded-lg bg-surface p-2 text-caption text-text-sub">
          {step.result_message}
        </div>
      )}

      {step.payload && Object.keys(step.payload).length > 0 && (
        <div className="mt-2">
          <div className="text-[0.6875rem] font-mono uppercase tracking-wider text-text-mute">
            payload
          </div>
          <PayloadPretty payload={step.payload} />
        </div>
      )}

      {step.feedback_messages && step.feedback_messages.length > 0 && (
        <div className="mt-2">
          <div className="text-[0.6875rem] font-mono uppercase tracking-wider text-text-mute">
            feedback ({step.feedback_messages.length})
          </div>
          <ul className="mt-1 space-y-0.5 text-caption text-text-sub">
            {step.feedback_messages.map((m, i) => (
              <li key={i} className="font-mono text-[0.75rem]">
                • {m}
              </li>
            ))}
          </ul>
        </div>
      )}
    </details>
  );
}

function PayloadPretty({
  payload,
}: {
  payload: { params?: Record<string, unknown> } | Record<string, unknown>;
}) {
  const params = ('params' in payload && payload.params) || payload;
  if (!params || Object.keys(params as object).length === 0) {
    return <span className="text-caption text-text-mute">(없음)</span>;
  }
  return (
    <pre className="mt-1 overflow-x-auto rounded-lg bg-surface-elev p-2 font-mono text-[0.75rem] leading-relaxed text-text-sub">
      {JSON.stringify(params, null, 2)}
    </pre>
  );
}

function formatDuration(d: HistoryDetail): string {
  if (!d.finished_at) return '진행 중';
  const start = new Date(d.started_at).getTime();
  const end = new Date(d.finished_at).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return '—';
  return `${((end - start) / 1000).toFixed(1)}s`;
}
