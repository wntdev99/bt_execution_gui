'use client';

import Link from 'next/link';
import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useAsync } from '@/hooks/useApi';
import { api, ApiError } from '@/api/client';
import { cn, formatTime } from '@/lib/utils';
import type { ScenarioListItem } from '@/lib/types';

/**
 * `/scenarios` — 시나리오 목록
 *
 * - 최신 수정 순 (backend storage 가 modified_at 으로 정렬)
 * - 카드 hover → /scenarios/[id]
 * - "새 시나리오 만들기" → /scenarios/new
 * - 카드 우측 작업: 실행 / 편집 / 삭제
 */
export default function ScenariosPage() {
  const list = useAsync(() => api.scenarios.list());
  const [confirmDelete, setConfirmDelete] = useState<ScenarioListItem | null>(null);

  return (
    <div className="flex flex-col gap-10">
      <header className="flex items-end justify-between gap-4">
        <div>
          <p className="text-caption font-mono uppercase tracking-widest text-text-mute">
            Scenarios
          </p>
          <h1 className="mt-2 text-display-xl text-text">저장된 시나리오</h1>
          <p className="mt-2 max-w-xl text-body text-text-sub">
            여러 트리를 순서대로 실행. 각 step 사이 대기 시간을 둘 수 있고, step-by-step 모드로 한 step 씩 진행할 수도 있습니다.
          </p>
        </div>
        <Link
          href="/scenarios/new"
          className="inline-flex h-11 items-center gap-2 rounded-full bg-text px-5 text-body font-semibold text-bg shadow-card hover:bg-accent"
        >
          + 새 시나리오
        </Link>
      </header>

      {list.error != null && (
        <div className="rounded-xl border border-danger/20 bg-danger-soft p-4 text-body text-danger">
          시나리오를 불러올 수 없습니다.
          <span className="ml-1 font-mono text-caption">({String(list.error)})</span>
        </div>
      )}

      {list.loading && !list.data && <SkeletonGrid />}

      {list.data && list.data.length === 0 && (
        <div className="rounded-2xl border border-dashed border-border bg-surface p-12 text-center">
          <p className="text-body text-text-sub">
            저장된 시나리오가 없습니다. 위의 <strong className="text-text">새 시나리오</strong> 로 시작하세요.
          </p>
        </div>
      )}

      {list.data && list.data.length > 0 && (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.data.map((sc, i) => (
            <ScenarioCard
              key={sc.id}
              item={sc}
              index={i}
              onDelete={() => setConfirmDelete(sc)}
            />
          ))}
        </section>
      )}

      <AnimatePresence>
        {confirmDelete && (
          <DeleteConfirm
            item={confirmDelete}
            onClose={() => setConfirmDelete(null)}
            onDone={() => {
              setConfirmDelete(null);
              list.refetch();
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function ScenarioCard({
  item,
  index,
  onDelete,
}: {
  item: ScenarioListItem;
  index: number;
  onDelete: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="flex h-full min-h-[180px] flex-col justify-between rounded-2xl bg-surface p-5 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-card-hover"
    >
      <Link href={`/scenarios/${encodeURIComponent(item.id)}`} className="flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-title text-text">{item.display_name}</h3>
          <span className="font-mono text-caption tabular text-text-mute">
            {item.step_count} step
          </span>
        </div>
        <p className="mt-2 line-clamp-3 text-caption text-text-sub">
          {item.description || <span className="text-text-mute">(설명 없음)</span>}
        </p>
      </Link>
      <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-caption text-text-mute">
        <span className="font-mono text-[0.6875rem] tabular">
          수정 {formatTime(item.modified_at)}
        </span>
        <div className="flex items-center gap-2">
          <Link
            href={`/scenarios/${encodeURIComponent(item.id)}/run`}
            className="rounded-full bg-accent-soft px-3 py-1 text-[0.75rem] font-semibold text-accent hover:bg-accent hover:text-white"
          >
            ▶ 실행
          </Link>
          <Link
            href={`/scenarios/${encodeURIComponent(item.id)}`}
            className="rounded-full px-2 py-1 text-[0.75rem] text-text-sub hover:bg-surface-elev"
          >
            편집
          </Link>
          <button
            onClick={onDelete}
            className="rounded-full px-2 py-1 text-[0.75rem] text-text-mute hover:bg-danger-soft hover:text-danger"
          >
            삭제
          </button>
        </div>
      </div>
    </motion.div>
  );
}

function DeleteConfirm({
  item,
  onClose,
  onDone,
}: {
  item: ScenarioListItem;
  onClose: () => void;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setErr(null);
    try {
      await api.scenarios.delete(item.id);
      onDone();
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.code ?? e.status} · ${e.message}`);
      else setErr(e instanceof Error ? e.message : '삭제 실패');
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
    >
      <motion.div
        initial={{ y: 8 }}
        animate={{ y: 0 }}
        exit={{ y: 8 }}
        className="w-[420px] rounded-2xl bg-surface p-6 shadow-elev"
      >
        <h2 className="text-title">시나리오 삭제</h2>
        <p className="mt-2 text-caption text-text-sub">
          <strong className="text-text">{item.display_name}</strong> ({item.id}) 을 삭제합니다.
          저장된 yaml 이 영구 삭제되며, 실행 이력은 보존됩니다.
        </p>
        {err && (
          <div className="mt-3 rounded-lg bg-danger-soft p-2 text-caption text-danger">{err}</div>
        )}
        <div className="mt-4 flex gap-2">
          <button
            onClick={onClose}
            disabled={busy}
            className="flex-1 rounded-full bg-surface-elev px-4 py-2.5 text-body font-medium text-text-sub hover:bg-border"
          >
            취소
          </button>
          <button
            onClick={confirm}
            disabled={busy}
            className={cn(
              'flex-1 rounded-full bg-danger px-4 py-2.5 text-body font-semibold text-white hover:bg-danger-hover',
              busy && 'opacity-50',
            )}
          >
            {busy ? '삭제 중…' : '삭제'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

function SkeletonGrid() {
  return (
    <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="h-[180px] animate-pulse rounded-2xl bg-surface-elev"
          style={{ animationDelay: `${i * 80}ms` }}
        />
      ))}
    </section>
  );
}
