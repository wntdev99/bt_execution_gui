import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format ETA (seconds) → "60초" / "3분" / "5분".
 */
export function formatEta(sec: number | null | undefined): string {
  if (!sec || sec <= 0) return '—';
  if (sec < 60) return `${sec}초`;
  const min = Math.round(sec / 60);
  return `${min}분`;
}

/**
 * Wrap a typed value in the bt_execution_server payload envelope.
 * int/double/bool/milliseconds/PoseStamped → typed object (B-22 회피).
 * string → bare scalar.
 */
export function toPayloadValue(
  type: string,
  value: unknown,
): unknown {
  if (value === undefined || value === null || value === '') return undefined;
  if (type === 'string') return value;
  return { type, value };
}

/**
 * Format timestamp (ISO or epoch ms) → "17:46:08".
 */
export function formatTime(ts: string | number | null | undefined): string {
  if (!ts) return '—';
  const d = typeof ts === 'number' ? new Date(ts) : new Date(ts);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}
