import { api, ApiError } from "./api.js";
import { $, describeError, el, showError } from "./ui.js";

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

// Плашка под шапкой: адрес не подтверждён, предлагаем отправить письмо
function addVerifyBanner(user) {
  if (!user.email || user.email_verified_at) return;
  const text = el("span", { text: "Подтвердите e-mail, чтобы получать напоминания." });
  const button = el("button", {
    class: "button-quiet",
    text: "Отправить письмо",
    attrs: { type: "button" },
  });
  const banner = el(
    "p",
    { class: "message message-info verify-banner", attrs: { role: "status" } },
    text,
    button,
  );
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await api("POST", "/auth/email-verification/request");
      text.textContent = "Письмо отправлено. Ссылка действует 24 часа. Проверьте и папку «Спам».";
      button.hidden = true;
    } catch (error) {
      if (redirectIfUnauthorized(error)) return;
      if (error instanceof ApiError && error.status === 409) {
        text.textContent = "Адрес уже подтверждён. Обновите страницу.";
        button.hidden = true;
        return;
      }
      text.textContent = describeError(error);
      button.disabled = false;
    }
  });
  document.querySelector(".topbar")?.after(banner);
}

// Шапка страниц после входа: e-mail пользователя, кнопка «Выйти», плашка подтверждения
export function initTopbar(user) {
  $("#user-email").textContent = user.email ?? user.username ?? "";
  $("#logout").addEventListener("click", async () => {
    try {
      await api("POST", "/auth/logout");
      location.replace("login.html");
    } catch (error) {
      showError($("#error"), describeError(error));
    }
  });
  addVerifyBanner(user);
}