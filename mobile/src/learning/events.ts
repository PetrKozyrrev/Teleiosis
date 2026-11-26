import { randomUUID } from 'expo-crypto';
import type { Request } from '../library/model';

export type LearningBudget = 5 | 15 | 30 | 60;
type LearningEvent =
  | { name: 'today_viewed' }
  | { name: 'saved_material_reopened' | 'next_action_opened'; material_id: number }
  | { name: 'time_budget_selected'; budget_minutes: LearningBudget; has_results: boolean }
  | { name: 'recommendation_opened'; budget_minutes: LearningBudget; material_id: number };

const maxIdle = 30 * 60 * 1000;
let visit: { owner: string; id: string; lastSeen: number; events: Map<string, { key: string; sent: boolean }> } | undefined;

export function resetLearningVisit() {
  visit = undefined;
}

export function trackLearning(request: Request, owner: string | null, event: LearningEvent) {
  if (process.env.EXPO_PUBLIC_LEARNING_METRICS !== '1' || !owner) return;
  const now = Date.now();
  if (!visit || visit.owner !== owner || now - visit.lastSeen >= maxIdle) {
    visit = { owner, id: randomUUID(), lastSeen: now, events: new Map() };
  }
  visit.lastSeen = now;
  const signature = JSON.stringify(event);
  const receipt = visit.events.get(signature) ?? { key: randomUUID(), sent: false };
  if (receipt.sent) return;
  visit.events.set(signature, receipt);
  receipt.sent = true;
  void request('/mobile/learning/events', 'POST', { ...event, visit_id: visit.id }, { idempotencyKey: receipt.key })
    .catch(() => { receipt.sent = false; });
}
