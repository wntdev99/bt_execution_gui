import { cn } from '@/lib/utils';

interface Props {
  status: 'idle' | 'running' | 'success' | 'failure' | 'cancelled';
  label?: string;
  className?: string;
}

const PALETTE = {
  idle: { dot: 'bg-text-mute', text: 'text-text-mute', ring: false },
  running: { dot: 'bg-running', text: 'text-running', ring: true },
  success: { dot: 'bg-success', text: 'text-success', ring: false },
  failure: { dot: 'bg-danger', text: 'text-danger', ring: false },
  cancelled: { dot: 'bg-text-sub', text: 'text-text-sub', ring: false },
} as const;

const LABELS: Record<Props['status'], string> = {
  idle: 'IDLE',
  running: 'RUNNING',
  success: 'SUCCESS',
  failure: 'FAILURE',
  cancelled: 'CANCELLED',
};

export function StatusPulse({ status, label, className }: Props) {
  const { dot, text, ring } = PALETTE[status];
  return (
    <div className={cn('inline-flex items-center gap-2', className)}>
      <span className={cn('relative inline-block w-2 h-2 rounded-full', dot, ring && 'pulse-ring')} />
      <span className={cn('text-caption font-mono tracking-wider', text)}>
        {label ?? LABELS[status]}
      </span>
    </div>
  );
}
