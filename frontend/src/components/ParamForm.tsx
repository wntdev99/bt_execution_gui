'use client';

/**
 * Dynamic param form for a tree manifest.
 *
 * Per-type input:
 *   - string         : bare scalar (text input)
 *   - int / double   : typed object {type, value} — numeric stepper
 *   - milliseconds   : typed object — number with "ms" suffix
 *   - bool           : typed object — toggle
 *   - PoseStamped    : typed object — x/y/yaw/frame_id (B-22 / docs §2.3)
 *
 * 서버 SSOT (handoff E-6): payload 조립 후 /api/trees/{id}/validate POST. 응답의
 * errors/warnings 를 UI 에 표시. validate OK → /api/execute 호출.
 */

import { useState, useTransition } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { api, ApiError } from '@/api/client';
import { cn } from '@/lib/utils';
import type { ParamSpec, TreeManifest } from '@/lib/types';

interface Props {
  manifest: TreeManifest;
  onSubmit?: (executionId: string) => void;
}

type FormValue = string | number | boolean | PoseValue | undefined;

interface PoseValue {
  x?: number;
  y?: number;
  yaw?: number;
  frame_id?: string;
}

function defaultValue(spec: ParamSpec): FormValue {
  if (spec.default !== null && spec.default !== undefined) {
    return spec.default as FormValue;
  }
  return undefined;
}

function buildPayload(specs: ParamSpec[], values: Record<string, FormValue>): {
  params: Record<string, unknown>;
} {
  const out: Record<string, unknown> = {};
  for (const spec of specs) {
    const v = values[spec.key];
    if (v === undefined || v === '' || v === null) continue;

    switch (spec.type) {
      case 'string':
        out[spec.key] = v;
        break;
      case 'int':
      case 'double':
        out[spec.key] = { type: spec.type, value: Number(v) };
        break;
      case 'milliseconds':
        out[spec.key] = { type: 'milliseconds', value: Number(v) };
        break;
      case 'bool':
        out[spec.key] = { type: 'bool', value: Boolean(v) };
        break;
      case 'PoseStamped': {
        const p = v as PoseValue;
        out[spec.key] = {
          type: 'PoseStamped',
          x: Number(p.x ?? 0),
          y: Number(p.y ?? 0),
          yaw: Number(p.yaw ?? 0),
          frame_id: p.frame_id ?? 'map',
        };
        break;
      }
    }
  }
  return { params: out };
}

export function ParamForm({ manifest, onSubmit }: Props) {
  const initial: Record<string, FormValue> = Object.fromEntries(
    manifest.params.map((p) => [p.key, defaultValue(p)]),
  );
  const [values, setValues] = useState<Record<string, FormValue>>(initial);
  const [errors, setErrors] = useState<string[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [submitErr, setSubmitErr] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function setField(key: string, v: FormValue) {
    setValues((prev) => ({ ...prev, [key]: v }));
    setErrors([]);
    setWarnings([]);
  }

  async function handleRun() {
    setErrors([]);
    setWarnings([]);
    setSubmitErr(null);
    const payload = buildPayload(manifest.params, values);
    startTransition(async () => {
      try {
        // 1. server-side validate (SSOT, handoff E-6)
        const v = await api.trees.validate(manifest.tree_id, payload);
        if (!v.ok) {
          setErrors(v.errors);
          setWarnings(v.warnings ?? []);
          return;
        }
        setWarnings(v.warnings ?? []);
        // 2. execute
        const res = await api.execute(manifest.tree_id, payload);
        onSubmit?.(res.execution_id);
      } catch (e) {
        if (e instanceof ApiError) {
          const detail = e.detail as { errors?: string[] } | undefined;
          if (detail?.errors) {
            setErrors(detail.errors);
          } else {
            setSubmitErr(e.message);
          }
        } else {
          setSubmitErr(e instanceof Error ? e.message : '실행 실패');
        }
      }
    });
  }

  return (
    <div className="flex flex-col gap-4">
      {manifest.params.length === 0 && (
        <div className="rounded-xl border border-border bg-surface-elev p-4 text-caption text-text-sub">
          입력 파라미터 없음. 바로 실행할 수 있습니다.
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {manifest.params.map((spec) => (
          <ParamRow
            key={spec.key}
            spec={spec}
            value={values[spec.key]}
            onChange={(v) => setField(spec.key, v)}
          />
        ))}
      </div>

      <AnimatePresence>
        {errors.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-xl border border-danger/20 bg-danger-soft p-3"
          >
            <div className="mb-1 text-caption font-semibold text-danger">
              검증 실패 ({errors.length})
            </div>
            <ul className="space-y-1 text-caption text-text">
              {errors.map((e, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-danger">▸</span>
                  <span>{e}</span>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>

      {warnings.length > 0 && (
        <div className="rounded-xl border border-warning/20 bg-warning-soft p-3">
          <div className="mb-1 text-caption font-semibold text-warning">
            경고 ({warnings.length})
          </div>
          <ul className="space-y-1 text-caption text-text-sub">
            {warnings.map((w, i) => (
              <li key={i}>⚠ {w}</li>
            ))}
          </ul>
        </div>
      )}

      {submitErr && (
        <div className="rounded-xl bg-danger-soft p-3 text-caption text-danger">
          {submitErr}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={handleRun}
          disabled={pending}
          className={cn(
            'inline-flex h-11 items-center gap-2 rounded-full px-6',
            'bg-text text-bg text-body font-semibold',
            'transition-all hover:bg-accent active:scale-95',
            manifest.dangerous && 'bg-warning hover:bg-warning/90 text-white',
            'disabled:opacity-50',
          )}
        >
          {pending ? '검증 중…' : manifest.dangerous ? '⚠ 위험 — 실행' : '실행'}
        </button>
        <span className="text-caption text-text-mute">
          서버 검증 후 즉시 실행됩니다.
        </span>
      </div>
    </div>
  );
}

/* ─────────────────────── Per-row inputs ─────────────────────── */

function ParamRow({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpec;
  value: FormValue;
  onChange: (v: FormValue) => void;
}) {
  const isPose = spec.type === 'PoseStamped';

  return (
    <div className={cn('flex flex-col gap-1.5 rounded-xl border border-border bg-surface p-3', isPose && 'md:col-span-2')}>
      <div className="flex items-baseline justify-between gap-2">
        <label className="flex items-center gap-2 text-caption font-semibold text-text">
          <span className="font-mono">{spec.key}</span>
          {spec.required && <span className="text-danger">*</span>}
          <TypeBadge type={spec.type} />
        </label>
        {spec.range && (
          <span className="font-mono text-[0.6875rem] tabular text-text-mute">
            [{spec.range[0]} – {spec.range[1]}]
          </span>
        )}
      </div>

      {spec.description && (
        <p className="text-[0.75rem] leading-snug text-text-sub">
          {spec.description.split('\n')[0]}
        </p>
      )}

      <ParamInput spec={spec} value={value} onChange={onChange} />

      {spec.note && (
        <p className="mt-1 rounded-md bg-warning-soft px-2 py-1 text-[0.6875rem] text-warning">
          ⚠ {spec.note.split('\n')[0]}
        </p>
      )}
    </div>
  );
}

function TypeBadge({ type }: { type: ParamSpec['type'] }) {
  return (
    <span className="rounded-md bg-surface-elev px-1.5 py-0.5 font-mono text-[0.6875rem] text-text-mute">
      {type}
    </span>
  );
}

function ParamInput({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpec;
  value: FormValue;
  onChange: (v: FormValue) => void;
}) {
  if (spec.enum && spec.enum.length > 0 && spec.type === 'string') {
    return (
      <select
        className="h-9 rounded-lg border border-border bg-bg px-3 text-body"
        value={(value as string) ?? ''}
        onChange={(e) => onChange(e.target.value || undefined)}
      >
        <option value="">— 선택 —</option>
        {spec.enum.map((opt) => (
          <option key={String(opt)} value={String(opt)}>
            {opt === '' ? '(기본)' : String(opt)}
          </option>
        ))}
      </select>
    );
  }

  switch (spec.type) {
    case 'string':
      return (
        <input
          type="text"
          className="h-9 rounded-lg border border-border bg-bg px-3 text-body"
          placeholder={(spec.default as string) ?? ''}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || undefined)}
        />
      );
    case 'int':
    case 'double':
    case 'milliseconds':
      return (
        <div className="relative">
          <input
            type="number"
            step={spec.type === 'double' ? '0.01' : '1'}
            className="h-9 w-full rounded-lg border border-border bg-bg px-3 pr-12 font-mono text-body tabular"
            placeholder={String(spec.default ?? '')}
            value={(value as number | undefined) ?? ''}
            onChange={(e) =>
              onChange(e.target.value === '' ? undefined : Number(e.target.value))
            }
          />
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 font-mono text-caption text-text-mute">
            {spec.type === 'milliseconds' ? 'ms' : spec.type}
          </span>
        </div>
      );
    case 'bool':
      return (
        <label className="inline-flex h-9 w-fit cursor-pointer items-center gap-2 rounded-lg border border-border bg-bg px-3">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
            className="h-4 w-4 accent-accent"
          />
          <span className="text-body">{value ? 'true' : 'false'}</span>
        </label>
      );
    case 'PoseStamped': {
      const p = (value as PoseValue | undefined) ?? {};
      return (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          <PoseField
            label="x"
            unit="m"
            value={p.x}
            onChange={(v) => onChange({ ...p, x: v })}
          />
          <PoseField
            label="y"
            unit="m"
            value={p.y}
            onChange={(v) => onChange({ ...p, y: v })}
          />
          <PoseField
            label="yaw"
            unit="rad"
            value={p.yaw}
            onChange={(v) => onChange({ ...p, yaw: v })}
          />
          <div className="flex flex-col gap-0.5">
            <label className="text-[0.6875rem] font-mono text-text-mute">frame_id</label>
            <input
              type="text"
              placeholder="map"
              className="h-8 rounded-md border border-border bg-bg px-2 font-mono text-caption"
              value={p.frame_id ?? ''}
              onChange={(e) => onChange({ ...p, frame_id: e.target.value })}
            />
          </div>
        </div>
      );
    }
  }
}

function PoseField({
  label,
  unit,
  value,
  onChange,
}: {
  label: string;
  unit: string;
  value: number | undefined;
  onChange: (v: number | undefined) => void;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <label className="font-mono text-[0.6875rem] text-text-mute">
        {label} <span className="text-text-sub">({unit})</span>
      </label>
      <input
        type="number"
        step="0.01"
        className="h-8 rounded-md border border-border bg-bg px-2 font-mono text-caption tabular"
        value={value ?? ''}
        onChange={(e) =>
          onChange(e.target.value === '' ? undefined : Number(e.target.value))
        }
      />
    </div>
  );
}
