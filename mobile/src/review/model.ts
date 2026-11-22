import { ApiError } from '../auth/api';
import { errorMessage } from '../library/model';

export type Card = {
  id: number; content_id: number; title: string; question: string; answer: string; takeaway: string;
  due_on: string; paused: boolean; stage: number; version: number;
};
export type CardPage = { items: Card[]; total: number; today: string };
export type HistoryPage = {
  items: { id: number; rating: 'again' | 'remembered'; due_on: string; occurred_at: string }[]; total: number;
};
export function reviewError(error: unknown, reading = false) {
  if (error instanceof ApiError && !error.gateway) {
    if (error.status === 404) return reading ? 'Для повторения карточек требуется обновление сервера.' : 'Карточка или материал больше недоступны.';
    if (error.status === 410) return 'Карточка удалена. Обновите список.';
    if (error.status === 412) return 'Карточка изменилась на другом устройстве. Обновите список.';
    if (error.status === 409) return 'Запрос не сохранён. Проверьте паузу карточки и лимит в 1000 карточек, затем обновите список.';
  }
  return errorMessage(error, 'Проверьте вопрос, ответ и дату.');
}
