'use client';

import Link from 'next/link';
import { motion } from 'motion/react';
import { TreeIcon } from './TreeIcon';
import { cn, formatEta } from '@/lib/utils';
import type { TreeListItem } from '@/lib/types';

interface Props {
  item: TreeListItem;
  index: number;
  href?: string;
}

/**
 * Dashboard 의 트리 카드.
 *
 * - 좌상단 tree icon (kind 별 SVG)
 * - dangerous flag → amber 우상단 hatch 배지 + 카드 border 강조
 * - 좌하단 param_count + ETA
 * - hover 시 elevation
 * - staggered fade-up (index * 60ms)
 */
export function TreeCard({ item, index, href }: Props) {
  const link = href ?? `/single?tree=${encodeURIComponent(item.tree_id)}`;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      <Link
        href={link}
        className={cn(
          'group relative flex h-full min-h-[180px] flex-col justify-between',
          'rounded-2xl bg-surface p-5 shadow-card',
          'transition-all duration-200 ease-out',
          'hover:-translate-y-0.5 hover:shadow-card-hover',
          item.dangerous && 'ring-1 ring-warning/30',
        )}
      >
        {item.dangerous && (
          <div
            className="absolute right-4 top-4 flex items-center gap-1.5 rounded-full bg-warning-soft px-2 py-1"
            title="위험 액션 — 실행 전 확인 모달"
          >
            <span className="hatch-warning inline-block h-2.5 w-2.5 rounded-sm" />
            <span className="text-[0.6875rem] font-semibold tracking-wider text-warning">
              위험
            </span>
          </div>
        )}

        <div>
          <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-surface-elev text-text-sub transition-colors group-hover:bg-accent-soft group-hover:text-accent">
            <TreeIcon treeId={item.tree_id} />
          </div>

          <h3 className="text-title text-text">{item.display_name}</h3>
          <p className="mt-1 line-clamp-2 text-caption text-text-sub">
            {item.description.split('\n')[0]}
          </p>
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
          <div className="flex items-center gap-3">
            <Spec label="입력" value={String(item.param_count)} />
            <Spec label="예상" value={formatEta(item.estimated_duration_sec)} />
          </div>
          <span className="font-mono text-caption text-text-mute transition-colors group-hover:text-accent">
            {item.tree_id}
            <span className="ml-1">→</span>
          </span>
        </div>
      </Link>
    </motion.div>
  );
}

function Spec({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1">
      <span className="text-[0.6875rem] uppercase tracking-wider text-text-mute">
        {label}
      </span>
      <span className="font-mono text-caption tabular text-text-sub">{value}</span>
    </span>
  );
}
