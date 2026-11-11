import { api } from "./api.js";

// Статистика текущего пользователя (GET /stats)
export function loadStats() {
  return api("GET", "/stats");
}

// Сколько материалов ещё ждёт изучения: не просмотрены и запланированы
export function pendingCount(stats) {
  return stats.by_status.unseen + stats.by_status.planned;
}

// Доля (0..1 или null) в целых процентах
export function percent(share) {
  return share === null ? null : Math.round(share * 100);
}