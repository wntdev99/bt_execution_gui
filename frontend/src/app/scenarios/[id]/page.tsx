'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAsync } from '@/hooks/useApi';
import { api } from '@/api/client';
import { ScenarioBuilder } from '@/components/ScenarioBuilder';
import { formatTime } from '@/lib/utils';

/**
 * `/scenarios/[id]` — 시나리오 상세 + 편집
 *
 * Builder 를 기존 scenario 로 prefill. 저장 시 If-Match 로 optimistic lock.
 */
export default function ScenarioDetailPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const id = decodeURIComponent(params.id);
  const { data, loading, error, refetch } = useAsync(
    () => api.scenarios.get(id),
    [id],
  );

  if (loading) return <div className="text-text-mute">로딩…</div>;
  if (error || !data) {
    return (
      <div className="rounded-xl border border-danger/20 bg-danger-soft p-4 text-body text-danger">
        시나리오를 찾을 수 없습니다.{' '}
        <span className="font-mono text-caption">{String(error)}</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between gap-3">
        <div>
          <p className="text-caption font-mono uppercase tracking-widest text-text-mute">
            Scenario · {data.id}
          </p>
          <h1 className="mt-2 text-display text-text">{data.display_name}</h1>
          <div className="mt-2 flex gap-4 text-caption text-text-mute">
            <span>step <span className="font-mono text-text">{data.steps.length}</span></span>
            <span>
              수정 <span className="font-mono">{formatTime(data.modified_at)}</span>
            </span>
            <span>schema v{data.schema_version}</span>
          </div>
        </div>
        <Link
          href={`/scenarios/${encodeURIComponent(data.id)}/run`}
          className="inline-flex h-11 items-center gap-2 rounded-full bg-accent px-5 text-body font-semibold text-white shadow-card hover:bg-accent-hover"
        >
          ▶ 실행
        </Link>
      </header>

      <ScenarioBuilder
        initial={data}
        onSaved={() => refetch()}
        onCancel={() => router.push('/scenarios')}
      />
    </div>
  );
}
