import { ApiError } from '../auth/api';
import type { Material, Request } from '../library/model';
import type { Job, JobState } from './store';

export const maxRetryAge = 14 * 24 * 60 * 60 * 1000;
type Outcome = { state: JobState; reason?: string; nextAt?: number; serverId?: number; material?: Material };

export async function dispatch(job: Job, ownerId: number, request: Request, now: number, jitter = Math.random): Promise<Outcome> {
  if (job.tried_at !== null && now - job.tried_at >= maxRetryAge) return { state: 'needs_action', reason: 'expired' };
  try {
    const result = await request('/contents/submissions', 'POST', JSON.parse(job.payload), {
      ownerId, idempotencyKey: job.id,
    }) as Material;
    if (!Number.isSafeInteger(result?.id) || result.id <= 0) throw new ApiError(502);
    return { state: 'synced', serverId: result.id, material: result };
  } catch (error) {
    if (!(error instanceof ApiError)) return { state: 'needs_action', reason: 'unknown' };
    if (error.gateway) return { state: 'needs_action', reason: 'gateway' };
    if (error.status === 401) return { state: 'needs_auth', nextAt: now + 2_000 };
    if (error.status === 409 && error.existingId) return { state: 'needs_action', reason: 'duplicate', serverId: error.existingId };
    if (error.status === 409) return { state: 'needs_action', reason: 'conflict' };
    if (error.status === 410) return { state: 'needs_action', reason: 'deleted' };
    if (error.status === 404) return { state: 'needs_action', reason: 'category' };
    if (error.status === 405) return { state: 'needs_action', reason: 'unavailable' };
    if (error.status === 422) return { state: 'needs_action', reason: 'invalid' };
    if (error.status === 0 || error.status === 429 || error.status >= 500) {
      const delay = Math.min(900_000, 2_000 * 2 ** Math.min(12, job.attempts - 1));
      return { state: 'retry_wait', reason: error.status === 429 ? 'rate' : 'network',
        nextAt: now + Math.max((error.retryAfter ?? 0) * 1000, Math.round(delay * (0.8 + jitter() * 0.4))) };
    }
    return { state: 'needs_action', reason: 'unknown' };
  }
}
