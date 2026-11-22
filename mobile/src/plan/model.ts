import { ApiError } from '../auth/api';
import { errorMessage } from '../library/model';

export const priorities = [
  { value: 1, label: 'Высокий' }, { value: 2, label: 'Обычный' }, { value: 3, label: 'Низкий' },
];
export type Goal = { id: number; name: string };
export type Task = {
  id: number; goal_id: number; goal_name: string; content_id: number; title: string;
  day: string; minutes: number; priority: number; version: number; completed_at: string | null;
};
export type Week = {
  week: string; end: string; today: string; budget: number | null; goals: Goal[]; tasks: Task[];
  summary: { total: number; done: number; planned_minutes: number; done_minutes: number; next_id: number | null };
};
export function shiftDay(day: string, days: number) {
  const date = new Date(day + 'T00:00:00Z');
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
export function validDay(day: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || day < '1900-01-01' || day > '2100-12-31') return false;
  return Number.isFinite(Date.parse(day)) && shiftDay(day, 0) === day;
}
export function minutesValid(value: string, limit: number) {
  return /^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= limit;
}
export function planError(error: unknown, reading = false) {
  if (error instanceof ApiError && !error.gateway) {
    if (error.status === 404) return reading ? 'Для недельного плана требуется обновление сервера.' : 'Запись удалена или недоступна. Обновите план.';
    if (error.status === 412) return 'План изменился на другом устройстве. Обновите план перед повтором.';
    if (error.code === 'already_planned') return 'В этой цели уже есть задание с этим материалом.';
    if (error.code === 'goal_limit') return 'Достигнут лимит в 100 целей.';
    if (error.code === 'task_completed') return 'Это задание уже завершено.';
  }
  return errorMessage(error, 'Проверьте дату, длительность и цель.');
}
