'use client';

import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAsync } from '@/hooks/useApi';
import { api } from '@/api/client';
import { TreeIcon } from '@/components/TreeIcon';
import { ParamForm } from '@/components/ParamForm';
import { ExecutionMonitor } from '@/components/ExecutionMonitor';
import { formatEta } from '@/lib/utils';

/**
 * `/single` — 단일 트리 실행
 *
 * Query param: ?tree=<TreeId>
 *
 * Layout:
 *   ┌─ 좌측 (8/12) ──────────────────────┬─ 우측 (4/12) ──┐
 *   │  트리 selector + manifest 정보       │  Execution     │
 *   │  ParamForm (동적, typed inputs)     │  Monitor       │
 *   └────────────────────────────────────┴────────────────┘
 */
export default function SinglePage() {
  return (
    <Suspense fallback={<div className="text-text-mute">로딩…</div>}>
      <SingleInner />
    </Suspense>
  );
}

function SingleInner() {
  const params = useSearchParams();
  const initial = params.get('tree') ?? '';
  const [selected, setSelected] = useState(initial);
  const [execId, setExecId] = useState<string | null>(null);

  const list = useAsync(() => api.trees.list());
  const detail = useAsync(
    () => (selected ? api.trees.get(selected) : Promise.resolve(null)),
    [selected],
  );
  const trees = list.data?.trees ?? [];

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      <section className="lg:col-span-8 flex flex-col gap-4">
        <header>
          <p className="text-caption font-mono uppercase tracking-widest text-text-mute">
            Single Execution
          </p>
          <h1 className="mt-2 text-display text-text">단일 실행</h1>
        </header>

        <div className="rounded-2xl bg-surface p-5 shadow-card">
          <label className="mb-2 block text-caption text-text-sub">트리 선택</label>
          <select
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              setExecId(null);
            }}
            className="h-11 w-full rounded-xl border border-border bg-bg px-4 font-mono text-body"
          >
            <option value="">— 선택 —</option>
            {trees.map((t) => (
              <option key={t.tree_id} value={t.tree_id}>
                {t.tree_id} — {t.display_name}
              </option>
            ))}
          </select>
        </div>

        {detail.data && (
          <div className="flex flex-col gap-4 rounded-2xl bg-surface p-5 shadow-card">
            <div className="flex items-start gap-4">
              <div className="grid h-12 w-12 place-items-center rounded-xl bg-surface-elev text-text-sub">
                <TreeIcon treeId={detail.data.tree_id} size={32} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h2 className="text-title text-text">{detail.data.display_name}</h2>
                  {detail.data.dangerous && (
                    <span className="rounded-full bg-warning-soft px-2 py-0.5 text-[0.6875rem] font-semibold text-warning">
                      위험
                    </span>
                  )}
                </div>
                <p className="mt-1 whitespace-pre-line text-caption text-text-sub">
                  {detail.data.description}
                </p>
                <div className="mt-2 flex gap-4 text-caption text-text-mute">
                  <span>
                    필수 입력{' '}
                    <span className="font-mono text-text">
                      {detail.data.params.filter((p) => p.required).length}
                    </span>
                  </span>
                  <span>
                    예상 시간{' '}
                    <span className="font-mono text-text">
                      {formatEta(detail.data.estimated_duration_sec)}
                    </span>
                  </span>
                </div>
              </div>
            </div>

            <ParamForm manifest={detail.data} onSubmit={setExecId} />
          </div>
        )}

        {!selected && (
          <div className="rounded-2xl border border-dashed border-border bg-surface-elev/50 p-12 text-center">
            <p className="text-body text-text-sub">
              위에서 실행할 트리를 선택하세요.
            </p>
          </div>
        )}
      </section>

      <aside className="lg:col-span-4 lg:sticky lg:top-20 lg:self-start">
        <h3 className="mb-2 text-caption font-mono uppercase tracking-widest text-text-mute">
          Monitor
        </h3>
        <ExecutionMonitor executionId={execId} />
      </aside>
    </div>
  );
}
