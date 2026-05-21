/**
 * Thin fetch wrapper for bt_web_bridge.
 *
 * Dev 환경에서 /api/* 는 next.config.mjs 의 rewrites 로 :8000 으로 proxy.
 * 운영 시 nginx 동일 origin.
 */
import type {
  TreeManifest,
  ServerStatus,
  ValidationResponse,
} from '@/lib/types';

const API_BASE = '/api';

class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let detail: unknown = text;
    try {
      detail = JSON.parse(text);
    } catch { /* ignore */ }
    throw new ApiError(res.status, `${res.status} ${res.statusText}`, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  trees: {
    list(): Promise<{ trees: TreeManifest[] }> {
      return request('/trees');
    },
    get(treeId: string): Promise<TreeManifest> {
      return request(`/trees/${encodeURIComponent(treeId)}`);
    },
    validate(treeId: string, payload: unknown): Promise<ValidationResponse> {
      return request(`/trees/${encodeURIComponent(treeId)}/validate`, {
        method: 'POST',
        body: JSON.stringify({ payload }),
      });
    },
  },
  status(): Promise<ServerStatus> {
    return request('/status');
  },
  execute(treeId: string, payload: unknown): Promise<{ execution_id: string }> {
    return request('/execute', {
      method: 'POST',
      body: JSON.stringify({ tree_id: treeId, payload }),
    });
  },
  cancel(executionId?: string): Promise<{ ok: true }> {
    return request('/execute/cancel', {
      method: 'POST',
      body: JSON.stringify(executionId ? { execution_id: executionId } : {}),
    });
  },
  emergencyStop(): Promise<{ ok: true; cancelled: string[] }> {
    return request('/emergency-stop', { method: 'POST' });
  },
};

export { ApiError };
