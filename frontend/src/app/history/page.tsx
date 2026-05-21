'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { useAsync } from '@/hooks/useApi';
import { api } from '@/api/client';
import { TreeIcon } from '@/components/TreeIcon';
import { cn, formatTime } from '@/lib/utils';
import type { HistoryListItem } from '@/lib/types';

/**
 * `/history` — 실행 이력
 *
 * - 최신 started_at 순 (backend ORDER BY started_at DESC)
 * - filter: all / single / scenario
 * - pagination: limit/offset (limit 50 fixed, page navigation)
 * - row 클릭 → /history/[id]
 */
const PAGE_SIZE = 50;

type KindFilter = 'all' | 'single' | 'scenario';

export default function HistoryPage() {
  const [kind, setKind] = useState<KindFilter>('all');
  const [page, setPage] = useState(0);

  const { data, loading, error, refetch } = useAsync(
    () =>
      api.history.list({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        kind: kind === 'all' ? undefined : kind,
      }),
    [kind, page],
  );

  const totalPages = useMemo(
    () => (data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1),
    [data],
  );

  return (
    <div className="flex flex-col gap-8">
      <header className="flex items-end justify-between gap-4">
        <div>
          <p className="text-caption font-mono uppercase tracking-widest text-text-mute">
            Execution History
          </p>
          <h1 className="mt-2 text-display-xl text-text">실행 이력</h1>
          <p className="mt-2 max-w-xl text-body text-text-sub">
            모든 단일/시나리오 실행이 sqlite 에 기록됩니다. 최신 {PAGE_SIZE} 건씩 표시.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="inline-flex h-9 items-center rounded-full bg-surface-elev px-4 text-caption text-text-sub hover:bg-border"
          title="새로고침"
        >
          ↻ 새로고침
        </button>
      </header>

      <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-surface p-3 shadow-card">
        <span className="ml-2 text-caption text-text-mute">유형</span>
        {(['all', 'single', 'scenario'] as KindFilter[]).map((k) => (
          <FilterChip
            key={k}
            selected={kind === k}
            onClick={() => {
              setKind(k);
              setPage(0);
            }}
          >
            {k === 'all' ? '전체' : k === 'single' ? '단일' : '시나리오'}
          </FilterChip>
        ))}
        <span className="ml-auto font-mono text-caption tabular text-text-mute">
          {data ? `${data.total} 건` : '—'}
        </span>
      </div>

      {error != null && (
        <div className="rounded-xl border border-danger/20 bg-danger-soft p-4 text-body text-danger">
          이력을 불러올 수 없습니다.{' '}
          <span className="font-mono text-caption">({String(error)})</span>
        </div>
      )}

      {loading && !data && <SkeletonRows />}

      {data && data.items.length === 0 && (
        <div className="rounded-2xl border border-dashed border-border bg-surface p-12 text-center">
          <p className="text-body text-text-sub">기록된 실행이 없습니다.</p>
        </div>
      )}

      {data && data.items.length > 0 && (
        <HistoryTable items={data.items} />
      )}

      {data && totalPages > 1 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          onChange={setPage}
        />
      )}
    </div>
  );
}

function FilterChip({
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
        'h-8 rounded-full px-3 text-caption font-medium transition-colors',
        selected
          ? 'bg-text text-bg'
          : 'bg-surface-elev text-text-sub hover:bg-border',
      )}
    >
      {children}
    </button>
  );
}

function HistoryTable({ items }: { items: HistoryListItem[] }) {
  return (
    <div className="overflow-hidden rounded-2xl bg-surface shadow-card">
      <table className="w-full table-fixed">
        <thead>
          <tr className="border-b border-border bg-surface-elev/50 text-left text-[0.6875rem] font-semibold uppercase tracking-wider text-text-mute">
            <th className="w-20 px-4 py-3">ID</th>
            <th className="w-32 px-3 py-3">유형</th>
            <th className="px-3 py-3">대상</th>
            <th className="w-40 px-3 py-3">시작</th>
            <th className="w-32 px-3 py-3">소요</th>
            <th className="w-32 px-3 py-3">결과</th>
            <th className="w-12 px-3 py-3" />
          </tr>
        </thead>
        <tbody>
          {items.map((row, i) => (
            <HistoryRow key={row.id} row={row} index={i} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HistoryRow({ row, index }: { row: HistoryListItem; index: number }) {
  const duration = useMemo(() => {
    if (!row.finished_at) return null;
    const start = new Date(row.started_at).getTime();
    const end = new Date(row.finished_at).getTime();
    if (Number.isNaN(start) || Number.isNaN(end)) return null;
    return (end - start) / 1000;
  }, [row.started_at, row.finished_at]);

  const target = row.kind === 'scenario' ? row.scenario_id : row.tree_id;

  return (
    <motion.tr
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: Math.min(index, 10) * 0.02 }}
      className="border-b border-border last:border-0"
    >
      <td className="px-4 py-2 font-mono text-caption tabular text-text-mute">
        #{row.id}
      </td>
      <td className="px-3 py-2">
        <KindBadge kind={row.kind} />
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center gap-2">
          {row.tree_id && (
            <span className="text-text-sub">
              <TreeIcon treeId={row.tree_id} size={16} />
            </span>
          )}
          <span className="font-mono text-caption text-text">
            {target ?? '(unknown)'}
          </span>
        </div>
      </td>
      <td className="px-3 py-2 font-mono text-caption tabular text-text-sub">
        {formatTime(row.started_at)}
      </td>
      <td className="px-3 py-2 font-mono text-caption tabular text-text-mute">
        {duration != null ? `${duration.toFixed(1)}s` : '—'}
      </td>
      <td className="px-3 py-2">
        <StatusChip status={row.final_status ?? 'UNKNOWN'} />
      </td>
      <td className="px-3 py-2 text-right">
        <Link
          href={`/history/${row.id}`}
          className="rounded-full px-2 py-1 text-caption text-accent hover:bg-accent-soft"
        >
          →
        </Link>
      </td>
    </motion.tr>
  );
}

function KindBadge({ kind }: { kind: 'single' | 'scenario' }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[0.6875rem] font-mono uppercase tracking-wider',
        kind === 'single' ? 'bg-accent-soft text-accent' : 'bg-warning-soft text-warning',
      )}
    >
      {kind}
    </span>
  );
}

function StatusChip({ status }: { status: string }) {
  const upper = status.toUpperCase();
  const palette: Record<string, string> = {
    SUCCESS: 'bg-success-soft text-success',
    FAILURE: 'bg-danger-soft text-danger',
    CANCELLED: 'bg-surface-elev text-text-sub',
    CRASHED: 'bg-danger-soft text-danger',
    PENDING: 'bg-surface-elev text-text-mute',
    RUNNING: 'bg-accent-soft text-accent',
    UNKNOWN: 'bg-surface-elev text-text-mute',
  };
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 font-mono text-[0.6875rem] tracking-wider',
        palette[upper] ?? 'bg-surface-elev text-text-mute',
      )}
    >
      {upper}
    </span>
  );
}

function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (p: number) => void;
}) {
  return (
    <div className="flex items-center justify-center gap-2 font-mono text-caption">
      <button
        disabled={page === 0}
        onClick={() => onChange(page - 1)}
        className="rounded-full bg-surface-elev px-3 py-1.5 text-text-sub hover:bg-border disabled:opacity-30"
      >
        ◂ 이전
      </button>
      <span className="px-3 text-text-mute tabular">
        {page + 1} / {totalPages}
      </span>
      <button
        disabled={page >= totalPages - 1}
        onClick={() => onChange(page + 1)}
        className="rounded-full bg-surface-elev px-3 py-1.5 text-text-sub hover:bg-border disabled:opacity-30"
      >
        다음 ▸
      </button>
    </div>
  );
}

function SkeletonRows() {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="h-12 animate-pulse rounded-xl bg-surface-elev"
          style={{ animationDelay: `${i * 60}ms` }}
        />
      ))}
    </div>
  );
}
