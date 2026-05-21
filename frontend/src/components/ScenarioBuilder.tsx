'use client';

/**
 * ScenarioBuilder — Scenario yaml 의 step list 편집기 (단순 ordering: up/down/remove).
 *
 * Step kinds:
 *   - action: tree_id + payload.params (ParamForm 의 buildParams 와 동일 형식)
 *   - wait: seconds
 *
 * - step_id 는 자동 생성 (step_<idx+1>) — 사용자 수정 가능
 * - 저장 시 POST /api/scenarios (신규) 또는 PUT /api/scenarios/{id} (수정, If-Match)
 * - dnd-kit 은 v2 polish — 본 1차는 ▲▼ 버튼 + 삭제 버튼만
 */

import { useEffect, useState, useTransition } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { api, ApiError } from '@/api/client';
import { useAsync } from '@/hooks/useApi';
import { cn } from '@/lib/utils';
import { TreeIcon } from './TreeIcon';
import type {
  Scenario,
  ScenarioStep,
  TreeDetail,
  TreeListItem,
  ParamSpec,
} from '@/lib/types';

interface Props {
  /** undefined = 신규 작성, Scenario = 기존 수정 */
  initial?: Scenario;
  onSaved: (sc: Scenario) => void;
  onCancel?: () => void;
}

interface BuilderState {
  display_name: string;
  description: string;
  steps: ScenarioStep[];
}

function blankAction(idx: number): ScenarioStep {
  return {
    kind: 'action',
    step_id: `step_${idx + 1}`,
    tree_id: '',
    payload: { params: {} },
  };
}
function blankWait(idx: number): ScenarioStep {
  return {
    kind: 'wait',
    step_id: `step_${idx + 1}`,
    seconds: 1.0,
  };
}

export function ScenarioBuilder({ initial, onSaved, onCancel }: Props) {
  const [state, setState] = useState<BuilderState>(() => ({
    display_name: initial?.display_name ?? '',
    description: initial?.description ?? '',
    steps: initial?.steps ?? [],
  }));
  const [errors, setErrors] = useState<string[]>([]);
  const [submitErr, setSubmitErr] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const trees = useAsync(() => api.trees.list()).data ?? [];

  function update<K extends keyof BuilderState>(key: K, val: BuilderState[K]) {
    setState((s) => ({ ...s, [key]: val }));
  }

  function addStep(kind: 'action' | 'wait') {
    setState((s) => ({
      ...s,
      steps: [
        ...s.steps,
        kind === 'action' ? blankAction(s.steps.length) : blankWait(s.steps.length),
      ],
    }));
  }

  function updateStep(idx: number, patch: Partial<ScenarioStep>) {
    setState((s) => ({
      ...s,
      steps: s.steps.map((st, i) => (i === idx ? { ...st, ...patch } : st)),
    }));
  }

  function removeStep(idx: number) {
    setState((s) => ({ ...s, steps: s.steps.filter((_, i) => i !== idx) }));
  }

  function moveStep(idx: number, delta: -1 | 1) {
    setState((s) => {
      const newIdx = idx + delta;
      if (newIdx < 0 || newIdx >= s.steps.length) return s;
      const next = [...s.steps];
      const [item] = next.splice(idx, 1);
      next.splice(newIdx, 0, item);
      return { ...s, steps: next };
    });
  }

  async function handleSave() {
    setErrors([]);
    setSubmitErr(null);
    // Client-side basic checks (server 가 SSOT)
    const errs: string[] = [];
    if (!state.display_name.trim()) errs.push('이름을 입력하세요.');
    if (state.steps.length === 0) errs.push('Step 을 1개 이상 추가하세요.');
    state.steps.forEach((s, i) => {
      if (!s.step_id.trim()) errs.push(`step[${i}]: step_id 비었음`);
      if (s.kind === 'action' && !s.tree_id) {
        errs.push(`step[${i}] (${s.step_id}): tree_id 비었음`);
      }
      if (s.kind === 'wait' && (s.seconds == null || s.seconds < 0)) {
        errs.push(`step[${i}] (${s.step_id}): seconds 가 0 이상이어야 함`);
      }
    });
    if (errs.length > 0) {
      setErrors(errs);
      return;
    }

    startTransition(async () => {
      try {
        let saved: Scenario;
        if (initial) {
          saved = await api.scenarios.update(
            initial.id,
            {
              display_name: state.display_name,
              description: state.description,
              steps: state.steps,
            },
            initial.modified_at,
          );
        } else {
          saved = await api.scenarios.create({
            display_name: state.display_name,
            description: state.description,
            steps: state.steps,
          });
        }
        onSaved(saved);
      } catch (e) {
        if (e instanceof ApiError) {
          const d = e.details as { errors?: string[] } | undefined;
          if (d?.errors) {
            setErrors(d.errors);
            return;
          }
          setSubmitErr(`${e.code ?? e.status} · ${e.message}`);
        } else {
          setSubmitErr(e instanceof Error ? e.message : '저장 실패');
        }
      }
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-2xl bg-surface p-5 shadow-card">
        <label className="text-caption font-mono text-text-mute">이름</label>
        <input
          type="text"
          className="mt-1 h-11 w-full rounded-xl border border-border bg-bg px-4 text-body"
          placeholder="예: 도킹 후 자동문 통과"
          value={state.display_name}
          onChange={(e) => update('display_name', e.target.value)}
        />
        <label className="mt-3 block text-caption font-mono text-text-mute">설명</label>
        <textarea
          className="mt-1 min-h-[68px] w-full resize-y rounded-xl border border-border bg-bg px-4 py-2 text-caption"
          placeholder="시나리오 목적 / 운영 메모 (선택)"
          value={state.description}
          onChange={(e) => update('description', e.target.value)}
        />
      </div>

      <div className="rounded-2xl bg-surface p-5 shadow-card">
        <div className="mb-3 flex items-baseline justify-between">
          <h3 className="text-title">Step ({state.steps.length})</h3>
          <div className="flex gap-2">
            <AddButton onClick={() => addStep('action')}>+ Action</AddButton>
            <AddButton onClick={() => addStep('wait')}>+ Wait</AddButton>
          </div>
        </div>

        {state.steps.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-surface-elev/50 p-10 text-center text-caption text-text-sub">
            Step 을 추가해 시나리오를 만드세요.
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <AnimatePresence initial={false}>
              {state.steps.map((step, idx) => (
                <motion.div
                  key={step.step_id + idx}
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <StepRow
                    idx={idx}
                    step={step}
                    trees={trees}
                    isFirst={idx === 0}
                    isLast={idx === state.steps.length - 1}
                    onChange={(patch) => updateStep(idx, patch)}
                    onMove={(delta) => moveStep(idx, delta)}
                    onRemove={() => removeStep(idx)}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
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

      {submitErr && (
        <div className="rounded-xl bg-danger-soft p-3 text-caption text-danger">
          {submitErr}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={pending}
          className="inline-flex h-11 items-center gap-2 rounded-full bg-text px-6 text-body font-semibold text-bg hover:bg-accent disabled:opacity-50"
        >
          {pending ? '저장 중…' : initial ? '저장' : '시나리오 만들기'}
        </button>
        {onCancel && (
          <button
            onClick={onCancel}
            disabled={pending}
            className="text-caption text-text-sub hover:text-text"
          >
            취소
          </button>
        )}
      </div>
    </div>
  );
}

function AddButton({
  onClick,
  children,
}: {
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className="rounded-full bg-surface-elev px-3 py-1.5 text-caption font-medium text-text-sub hover:bg-accent-soft hover:text-accent"
    >
      {children}
    </button>
  );
}

/* ─────────────────── per-step row ─────────────────── */

function StepRow({
  idx,
  step,
  trees,
  isFirst,
  isLast,
  onChange,
  onMove,
  onRemove,
}: {
  idx: number;
  step: ScenarioStep;
  trees: TreeListItem[];
  isFirst: boolean;
  isLast: boolean;
  onChange: (patch: Partial<ScenarioStep>) => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-3">
      <div className="flex items-start gap-2">
        <div className="flex flex-col gap-0.5">
          <IconButton onClick={() => onMove(-1)} disabled={isFirst} title="위로">
            ▲
          </IconButton>
          <IconButton onClick={() => onMove(1)} disabled={isLast} title="아래로">
            ▼
          </IconButton>
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-md bg-surface-elev font-mono text-[0.75rem] text-text-sub">
              {idx + 1}
            </span>
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-[0.6875rem] font-mono uppercase tracking-wider',
                step.kind === 'action'
                  ? 'bg-accent-soft text-accent'
                  : 'bg-warning-soft text-warning',
              )}
            >
              {step.kind}
            </span>
            <input
              type="text"
              value={step.step_id}
              onChange={(e) => onChange({ step_id: e.target.value })}
              className="h-7 flex-1 rounded-md border border-border bg-bg px-2 font-mono text-caption"
              placeholder="step_id"
            />
            <IconButton onClick={onRemove} title="삭제" danger>
              ✕
            </IconButton>
          </div>

          <div className="mt-3">
            {step.kind === 'action' ? (
              <ActionStepBody step={step} trees={trees} onChange={onChange} />
            ) : (
              <WaitStepBody step={step} onChange={onChange} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function IconButton({
  onClick,
  disabled,
  title,
  danger,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  title?: string;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        'grid h-6 w-6 place-items-center rounded-md text-[0.75rem] font-mono transition-colors',
        'text-text-mute hover:bg-surface-elev hover:text-text',
        danger && 'hover:bg-danger-soft hover:text-danger',
        disabled && 'opacity-30 cursor-not-allowed hover:bg-transparent hover:text-text-mute',
      )}
    >
      {children}
    </button>
  );
}

function WaitStepBody({
  step,
  onChange,
}: {
  step: ScenarioStep;
  onChange: (patch: Partial<ScenarioStep>) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-caption text-text-sub">대기 시간</label>
      <input
        type="number"
        step="0.1"
        min={0}
        value={step.seconds ?? ''}
        onChange={(e) =>
          onChange({ seconds: e.target.value === '' ? null : Number(e.target.value) })
        }
        className="h-9 w-24 rounded-lg border border-border bg-bg px-3 font-mono text-body tabular"
      />
      <span className="font-mono text-caption text-text-mute">sec</span>
    </div>
  );
}

function ActionStepBody({
  step,
  trees,
  onChange,
}: {
  step: ScenarioStep;
  trees: TreeListItem[];
  onChange: (patch: Partial<ScenarioStep>) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <label className="text-caption text-text-sub">트리</label>
        <select
          value={step.tree_id ?? ''}
          onChange={(e) => onChange({ tree_id: e.target.value || null })}
          className="h-9 flex-1 rounded-lg border border-border bg-bg px-3 font-mono text-body"
        >
          <option value="">— 선택 —</option>
          {trees.map((t) => (
            <option key={t.tree_id} value={t.tree_id}>
              {t.tree_id} — {t.display_name}
            </option>
          ))}
        </select>
        {step.tree_id && (
          <span className="text-text-sub">
            <TreeIcon treeId={step.tree_id} size={20} />
          </span>
        )}
      </div>

      {step.tree_id && (
        <ActionStepParams treeId={step.tree_id} step={step} onChange={onChange} />
      )}
    </div>
  );
}

function ActionStepParams({
  treeId,
  step,
  onChange,
}: {
  treeId: string;
  step: ScenarioStep;
  onChange: (patch: Partial<ScenarioStep>) => void;
}) {
  const { data: detail, loading } = useAsync(
    () => api.trees.get(treeId),
    [treeId],
  );

  if (loading) {
    return <div className="text-[0.75rem] text-text-mute">manifest 로딩…</div>;
  }
  if (!detail) return null;

  const currentParams = step.payload?.params ?? {};

  function setParam(key: string, value: unknown) {
    const nextParams = { ...currentParams };
    if (value === undefined || value === null) {
      delete nextParams[key];
    } else {
      nextParams[key] = value;
    }
    onChange({ payload: { params: nextParams } });
  }

  return (
    <details className="rounded-lg border border-border bg-surface-elev/50 p-2 open:bg-surface-elev/70">
      <summary className="cursor-pointer text-caption text-text-sub">
        파라미터 ({detail.params.filter((p) => p.required).length} 필수
        / {detail.params.length} 전체)
      </summary>
      <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
        {detail.params.map((spec) => (
          <ParamRow
            key={spec.key}
            spec={spec}
            value={currentParams[spec.key]}
            onChange={(v) => setParam(spec.key, v)}
          />
        ))}
      </div>
    </details>
  );
}

/* Inline param input — Scenario builder 안에서 payload.params 값 그대로 저장.
   (typed object / bare scalar 형식은 사용자가 ParamForm 의 typed input UX 와
   다르게 단순 JSON 직접 입력하도록 함 — 빌더 UX 의 1차 단순 패턴) */
function ParamRow({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpec;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  // 사용자에게는 typed value 의 inner value 노출 (편집 친화).
  const inner = extractInner(value, spec);
  const [text, setText] = useState<string>(stringify(inner));
  useEffect(() => {
    setText(stringify(extractInner(value, spec)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(value)]);

  return (
    <div className="flex flex-col gap-0.5">
      <label className="flex items-center gap-1 text-[0.75rem]">
        <span className="font-mono text-text">{spec.key}</span>
        {spec.required && <span className="text-danger">*</span>}
        <span className="rounded bg-bg px-1 font-mono text-[0.625rem] text-text-mute">
          {spec.type}
        </span>
      </label>
      <input
        type="text"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          onChange(packTyped(e.target.value, spec));
        }}
        placeholder={
          spec.type === 'PoseStamped'
            ? 'x,y,yaw,frame_id (예: 1.5,2.0,0,map)'
            : String(spec.default ?? '')
        }
        className="h-8 rounded-md border border-border bg-bg px-2 font-mono text-caption tabular"
      />
    </div>
  );
}

function extractInner(value: unknown, spec: ParamSpec): unknown {
  if (value === undefined || value === null) return '';
  if (spec.type === 'string') return value;
  if (typeof value === 'object' && value !== null && 'type' in (value as object)) {
    const v = value as Record<string, unknown>;
    if (spec.type === 'PoseStamped') {
      return `${v.x ?? 0},${v.y ?? 0},${v.yaw ?? 0},${v.frame_id ?? 'map'}`;
    }
    return v.value ?? '';
  }
  return value;
}

function stringify(v: unknown): string {
  if (v === undefined || v === null) return '';
  if (typeof v === 'string') return v;
  return String(v);
}

function packTyped(text: string, spec: ParamSpec): unknown {
  const trimmed = text.trim();
  if (trimmed === '') return undefined;
  switch (spec.type) {
    case 'string':
      return trimmed;
    case 'int':
    case 'double':
    case 'milliseconds': {
      const n = Number(trimmed);
      if (Number.isNaN(n)) return undefined;
      return { type: spec.type, value: n };
    }
    case 'bool': {
      const lo = trimmed.toLowerCase();
      const b = lo === 'true' || lo === '1' || lo === 'yes';
      return { type: 'bool', value: b };
    }
    case 'PoseStamped': {
      const parts = trimmed.split(',').map((s) => s.trim());
      const x = Number(parts[0] ?? 0);
      const y = Number(parts[1] ?? 0);
      const yaw = Number(parts[2] ?? 0);
      const frame_id = parts[3] || 'map';
      return { type: 'PoseStamped', x, y, yaw, frame_id };
    }
  }
}
