/**
 * Thin fetch wrapper for bt_web_bridge.
 *
 * 모든 응답이 ApiOk envelope (`{ok, data}`) 또는 ApiErr (`{ok: false, error}`).
 * `request<T>` 가 envelope unwrap — caller 는 data 직접 받음.
 *
 * Dev 환경에서 /api/* 는 next.config.mjs 의 rewrites 로 :8000 으로 proxy.
 * 운영 시 nginx 동일 origin.
 */
import type {
  TreeListItem,
  TreeDetail,
  ServerStatus,
  ValidateResponse,
  ExecuteResponse,
  ApiErr,
  Scenario,
  ScenarioListItem,
  ScenarioRunResponse,
  ScenarioStep,
  HistoryListResponse,
  HistoryDetail,
} from '@/lib/types';

const API_BASE = '/api';

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code: string | null,
    public details?: unknown,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  const text = await res.text().catch(() => '');
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const err = body as ApiErr | { detail?: { code?: string; message?: string; details?: unknown } } | null;
    if (err && typeof err === 'object' && 'ok' in err && err.ok === false) {
      throw new ApiError(res.status, err.error.message, err.error.code, err.error.details);
    }
    // FastAPI HTTPException → {detail: {...}} 형식
    if (err && typeof err === 'object' && 'detail' in err && err.detail) {
      const d = err.detail as { code?: string; message?: string; details?: unknown };
      throw new ApiError(res.status, d.message ?? res.statusText, d.code ?? null, d.details);
    }
    throw new ApiError(res.status, `${res.status} ${res.statusText}`, null, body);
  }
  // Success — envelope unwrap.
  if (body && typeof body === 'object' && 'ok' in body) {
    const env = body as { ok: boolean; data?: T };
    if (env.ok && 'data' in env) {
      return env.data as T;
    }
  }
  return body as T;
}

export const api = {
  trees: {
    list(): Promise<TreeListItem[]> {
      return request('/trees');
    },
    get(treeId: string): Promise<TreeDetail> {
      return request(`/trees/${encodeURIComponent(treeId)}`);
    },
    /**
     * /api/trees/{id}/validate body: `{params: {...}}` (payload.params 직접).
     */
    validate(treeId: string, params: Record<string, unknown>): Promise<ValidateResponse> {
      return request(`/trees/${encodeURIComponent(treeId)}/validate`, {
        method: 'POST',
        body: JSON.stringify({ params }),
      });
    },
  },
  status(): Promise<ServerStatus> {
    return request('/status');
  },
  /**
   * /api/execute body: `{tree_id, payload: {params: {...}}}`.
   */
  execute(treeId: string, params: Record<string, unknown>): Promise<ExecuteResponse> {
    return request('/execute', {
      method: 'POST',
      body: JSON.stringify({ tree_id: treeId, payload: { params } }),
    });
  },
  cancel(executionId?: string): Promise<{ cancelled: string | null }> {
    return request('/execute/cancel', {
      method: 'POST',
      body: JSON.stringify(executionId ? { execution_id: executionId } : {}),
    });
  },
  emergencyStop(): Promise<{ cancelled: string[] | null }> {
    return request('/emergency-stop', { method: 'POST' });
  },

  /* ── Scenarios CRUD + run controls ── */
  scenarios: {
    list(): Promise<ScenarioListItem[]> {
      return request('/scenarios');
    },
    get(scenarioId: string): Promise<Scenario> {
      return request(`/scenarios/${encodeURIComponent(scenarioId)}`);
    },
    create(body: {
      display_name: string;
      description?: string;
      steps: ScenarioStep[];
    }): Promise<Scenario> {
      return request('/scenarios', {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    /**
     * @param ifMatch Optimistic-lock token (modified_at ISO of the loaded scenario).
     */
    update(
      scenarioId: string,
      body: {
        display_name?: string;
        description?: string;
        steps?: ScenarioStep[];
      },
      ifMatch?: string,
    ): Promise<Scenario> {
      const headers: Record<string, string> = {};
      if (ifMatch) headers['If-Match'] = ifMatch;
      return request(`/scenarios/${encodeURIComponent(scenarioId)}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(body),
      });
    },
    delete(scenarioId: string): Promise<{ deleted: string }> {
      return request(`/scenarios/${encodeURIComponent(scenarioId)}`, {
        method: 'DELETE',
      });
    },
    run(
      scenarioId: string,
      mode: 'auto' | 'step_by_step' = 'auto',
      repeatCount = 1,
    ): Promise<ScenarioRunResponse> {
      return request(`/scenarios/${encodeURIComponent(scenarioId)}/run`, {
        method: 'POST',
        body: JSON.stringify({ mode, repeat_count: repeatCount }),
      });
    },
    /* Run controls — endpoints under /api/scenarios/run/* */
    pause(): Promise<{ execution_id: string; will_pause_after_current_step: boolean }> {
      return request('/scenarios/run/pause', { method: 'POST' });
    },
    resume(): Promise<{ execution_id: string; resumed: boolean }> {
      return request('/scenarios/run/resume', { method: 'POST' });
    },
    next(): Promise<{ execution_id: string; advanced: boolean }> {
      return request('/scenarios/run/next', { method: 'POST' });
    },
    cancelRun(): Promise<{ execution_id: string; cancelling: boolean }> {
      return request('/scenarios/run/cancel', { method: 'POST' });
    },
  },

  /* ── Execution history ── */
  history: {
    list(opts: {
      limit?: number;
      offset?: number;
      kind?: 'single' | 'scenario';
      scenario_id?: string;
    } = {}): Promise<HistoryListResponse> {
      const params = new URLSearchParams();
      if (opts.limit != null) params.set('limit', String(opts.limit));
      if (opts.offset != null) params.set('offset', String(opts.offset));
      if (opts.kind) params.set('kind', opts.kind);
      if (opts.scenario_id) params.set('scenario_id', opts.scenario_id);
      const qs = params.toString();
      return request(`/history${qs ? `?${qs}` : ''}`);
    },
    get(executionId: number): Promise<HistoryDetail> {
      return request(`/history/${encodeURIComponent(String(executionId))}`);
    },
  },
};

export { ApiError };
