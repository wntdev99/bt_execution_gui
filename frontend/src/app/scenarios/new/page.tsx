'use client';

import { useRouter } from 'next/navigation';
import { ScenarioBuilder } from '@/components/ScenarioBuilder';

/**
 * `/scenarios/new` — 새 시나리오 빌더
 *
 * 저장 성공 시 detail 페이지 (/scenarios/[id]) 로 이동.
 */
export default function NewScenarioPage() {
  const router = useRouter();

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="text-caption font-mono uppercase tracking-widest text-text-mute">
          New Scenario
        </p>
        <h1 className="mt-2 text-display text-text">새 시나리오</h1>
        <p className="mt-2 max-w-xl text-body text-text-sub">
          여러 트리를 순서대로 실행하도록 시나리오를 작성하세요. 각 step 사이에 대기 시간을 둘 수 있습니다.
        </p>
      </header>

      <ScenarioBuilder
        onSaved={(sc) => router.push(`/scenarios/${encodeURIComponent(sc.id)}`)}
        onCancel={() => router.push('/scenarios')}
      />
    </div>
  );
}
