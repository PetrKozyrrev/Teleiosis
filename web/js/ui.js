import { ApiError } from "./api.js";

export const PASSWORD_MIN = 10;
export const PASSWORD_MAX = 128;
const GENERIC = "Не получилось выполнить действие. Обновите страницу и повторите.";

export const $ = (selector, root = document) => root.querySelector(selector);

// Любой текст выводится только через textContent: чужая разметка не исполняется.
export function showError(element, text) {
  element.textContent = text;
  element.hidden = false;
}
export const showInfo = showError;

export function hideMessage(element) {
  element.textContent = "";
  element.hidden = true;
}

function formatWait(seconds) {
  if (!seconds) return "позже";
  const minutes = Math.ceil(seconds / 60);
  if (minutes <= 1) return "через минуту";
  if (minutes < 60) return `через ${minutes} мин.`;
  return `через ${Math.ceil(minutes / 60)} ч.`;
}

// Текст ошибки по коду ответа. overrides: { 401: "…" } для конкретной формы.
export function describeError(error, overrides = {}) {
  if (!(error instanceof ApiError)) return GENERIC;
  const { status } = error;
  if (status in overrides) return overrides[status];
  if (status === 0) return "Нет связи с сервером. Проверьте интернет и повторите.";
  if (status === 429) return `Слишком много попыток. Повторите ${formatWait(error.retryAfter)}.`;
  if (status === 403) return "Запрос отклонён. Обновите страницу и повторите.";
  if (status === 422) return "Проверьте введённые данные.";
  if (status >= 500) return "Сервис временно недоступен. Попробуйте чуть позже.";
  return GENERIC;
}

// Длина считается в символах, как на сервере (эмодзи это один символ)
export function passwordProblem(value) {
  const length = Array.from(value).length;
  if (length < PASSWORD_MIN) return `Пароль должен быть не короче ${PASSWORD_MIN} символов.`;
  if (length > PASSWORD_MAX) return `Пароль должен быть не длиннее ${PASSWORD_MAX} символов.`;
  return null;
}

function setBusy(form, busy) {
  form.setAttribute("aria-busy", String(busy));
  for (const button of form.querySelectorAll("button[type=submit]")) {
    button.disabled = busy;
    if (busy) {
      button.dataset.label = button.textContent;
      button.textContent = "Подождите…";
    } else if (button.dataset.label) {
      button.textContent = button.dataset.label;
    }
  }
}

// Отправка формы без перезагрузки страницы и без двойной отправки
export function onSubmit(form, handler) {
  let running = false;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (running) return;
    running = true;
    setBusy(form, true);
    try {
      await handler();
    } finally {
      running = false;
      setBusy(form, false);
    }
  });
}

export function attachPasswordToggle(button, input) {
  button.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.textContent = show ? "Скрыть" : "Показать";
    button.setAttribute("aria-label", show ? "Скрыть пароль" : "Показать пароль");
  });
}

// Создаёт элемент. Текст ставится только через textContent, пустые дочерние узлы пропускаются.
export function el(tag, options = {}, ...children) {
  const node = document.createElement(tag);
  if (options.class) node.className = options.class;
  if (options.text !== undefined) node.textContent = options.text;
  for (const [name, value] of Object.entries(options.attrs ?? {})) node.setAttribute(name, value);
  node.append(...children.filter(Boolean));
  return node;
}

// Адрес для ссылки: только http и https, иначе null
export function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

// Обрезка по символам (эмодзи не рвётся посередине)
export function shorten(text, limit) {
  const chars = Array.from(text);
  return chars.length <= limit ? text : `${chars.slice(0, limit - 1).join("")}…`;
}