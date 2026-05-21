'use client';

import { useAsync } from '@/hooks/useApi';
import { api } from '@/api/client';
import { TreeCard } from '@/components/TreeCard';

/**
 * `/` Dashboard
 *
 * - 트리 카드 grid (운영 GUI 노출 root tree 자동 fetch)
 * - 카드 hover → /single?tree=... 라우팅
 * - server status badge (bt_schema_server / bt_execution_server reachability + tree_count)
 */
export default function DashboardPage() {
  const { data: trees, loading, error } = useAsync(() => api.trees.list());
  const list = trees ?? [];

  return (
    <div className="flex flex-col gap-10">
      <header className="flex items-end justify-between gap-4">
        <div>
          <p className="text-caption font-mono uppercase tracking-widest text-text-mute">
            Operations Console
          </p>
          <h1 className="mt-2 text-display-xl text-text">실행 가능한 동작</h1>
          <p className="mt-2 max-w-xl text-body text-text-sub">
            각 카드를 선택해 단일 실행으로 진입하거나, 시나리오 빌더에서 조합해 사용하세요.
          </p>
        </div>

        <ServerBadge />
      </header>

      {error != null && (
        <div className="rounded-xl border border-danger/20 bg-danger-soft p-4 text-body text-danger">
          백엔드에 연결할 수 없습니다. bt_web_bridge 가 실행 중인지 확인하세요.
          <span className="ml-1 font-mono text-caption">({String(error)})</span>
        </div>
      )}

      {loading && list.length === 0 && <SkeletonGrid />}

      {list.length > 0 && (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((m, i) => (
            <TreeCard key={m.tree_id} item={m} index={i} />
          ))}
        </section>
      )}

      {!loading && list.length === 0 && !error && (
        <div className="rounded-2xl border border-dashed border-border bg-surface p-12 text-center">
          <p className="text-body text-text-sub">
            등록된 트리가 없습니다. bt_schema_server 의 <code className="font-mono">exposed_tree_ids</code> 와
            <code className="font-mono"> bt_web_bridge/manifests/</code> 를 확인하세요.
          </p>
        </div>
      )}
    </div>
  );
}

function ServerBadge() {
  const { data } = useAsync(() => api.status(), []);
  if (!data) return null;
  const schemaOk = data.bt_schema_server === 'reachable';
  const execOk = data.bt_execution_server === 'reachable';
  const ok = schemaOk && execOk;
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-border bg-surface px-4 py-3">
      <span className={`relative inline-block h-2 w-2 rounded-full ${ok ? 'bg-success' : 'bg-warning'}`}>
        {ok && <span className="absolute inset-0 animate-pulse rounded-full bg-success" />}
      </span>
      <div className="text-right">
        <div className="font-mono text-caption tabular text-text">
          {data.tree_count} trees
        </div>
        <div className="text-[0.6875rem] text-text-mute">
          {ok ? 'ROS 연결' : `${schemaOk ? '' : 'schema '}${execOk ? '' : 'exec '}연결 불안정`}
        </div>
      </div>
    </div>
  );
}

function SkeletonGrid() {
  return (
    <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-[180px] animate-pulse rounded-2xl bg-surface-elev"
          style={{ animationDelay: `${i * 80}ms` }}
        />
      ))}
    </section>
  );
}
