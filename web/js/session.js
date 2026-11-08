import { api, ApiError } from "./api.js";

// Текущий пользователь или null, если вход не выполнен
export async function currentUser() {
  try {
    return await api("GET", "/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

// Для страниц после входа: без сессии переходит на вход и останавливает скрипт
export async function requireUser() {
  const user = await currentUser();
  if (!user) {
    location.replace("login.html");
    return new Promise(() => {});
  }
  return user;
}

// Для страниц входа и регистрации: уже вошедшего отправляет в библиотеку
export async function redirectIfSignedIn() {
  try {
    if (await currentUser()) location.replace("./");
  } catch {
    // нет связи: оставляем форму, ошибку покажет отправка
  }
}


// Если сессия кончилась (401), отправляет на вход и возвращает true
export function redirectIfUnauthorized(error) {
  if (error instanceof ApiError && error.status === 401) {
    location.replace("login.html");
    return true;
  }
  return false;
}