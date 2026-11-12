import { api, ApiError } from "./api.js";
import { SOURCE_LABELS, bindOpenTracking, formatDate, hostOf } from "./cards.js";
import { initTopbar, redirectIfUnauthorized, requireUser } from "./session.js";
import {
  $, describeError, el, hideMessage, markReady, onSubmit, safeHttpUrl, showError, showInfo,
} from "./ui.js";

const id = new URLSearchParams(location.search).get("id") ?? "";
const path = `/contents/${encodeURIComponent(id)}`;
const reminderPath = `${path}/reminder`;
let user = null;
let item = null;
let reminder = null;
let categoryList = [];
let categories = new Map();

const itemError = $("#item-error");
const editError = $("#edit-error");
const editInfo = $("#edit-info");
const categoryError = $("#category-error");
const categoryNote = $("#category-note");
const categorySelect = $("#item-category");
const titleInput = $("#edit-title");
const noteInput = $("#edit-note");
const statusButtons = [...document.querySelectorAll(".status-button")];

const reminderError = $("#reminder-error");
const reminderStatus = $("#reminder-status");
const reminderHint = $("#reminder-hint");
const reminderInput = $("#reminder-at");
const reminderClear = $("#reminder-clear");
const presetButtons = [...document.querySelectorAll("[data-preset]")];

const dateTimeFormat = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function showMissing() {
  $("#item").hidden = true;
  showError($("#missing"), "Материал не найден. Возможно, он был удалён.");
}

function render() {
  document.title = `${item.title} — Teleiosis`;
  $("#item-title").textContent = item.title;

  const source = item.source in SOURCE_LABELS ? item.source : "other";
  const href = item.url ? safeHttpUrl(item.url) : null;
  const category = item.category_id != null ? categories.get(item.category_id) : null;
  const parts = [SOURCE_LABELS[source], href && hostOf(href), category, `Добавлено ${formatDate(item.created_at)}`];
  $("#item-meta").replaceChildren(
    ...parts.filter(Boolean).map((text) => {
      const span = document.createElement("span");
      span.textContent = text;
      return span;
    }),
  );

  const link = $("#item-link");
  link.hidden = !href;
  if (href) {
    link.href = href;
    link.dataset.openId = String(item.id);
  }
  const description = $("#item-description");
  description.hidden = !item.description;
  description.textContent = item.description ?? "";

  for (const button of statusButtons) {
    button.setAttribute("aria-pressed", String(button.dataset.status === item.status));
  }
  $("#status-note").textContent =
    item.status === "studied" && item.studied_at ? `Изучено ${formatDate(item.studied_at)}.` : "";

  $("#opens").textContent =
    item.open_count > 0
      ? `Открытий оригинала: ${item.open_count}. Последнее: ${formatDate(item.last_opened_at)}.`
      : item.url
        ? "Оригинал ещё не открывали."
        : "";
}

function fillForm() {
  titleInput.value = item.title;
  noteInput.value = item.note ?? "";
}

function fillCategorySelect() {
  categorySelect.replaceChildren(
    el("option", { text: "Без категории", attrs: { value: "" } }),
    ...categoryList.map((c) => el("option", { text: c.name, attrs: { value: String(c.id) } })),
  );
  categorySelect.value = item.category_id != null ? String(item.category_id) : "";
}

// Обновляет счётчики после открытия оригинала, не трогая поля формы
async function refresh() {
  try {
    item = await api("GET", path);
    render();
  } catch {
    // остаются прежние данные
  }
}

async function loadCategories() {
  try {
    categoryList = await api("GET", "/categories");
    categories = new Map(categoryList.map((c) => [c.id, c.name]));
  } catch {
    // без категорий страница работает
  }
}

async function changeStatus(status) {
  if (status === item.status) return;
  hideMessage(itemError);
  statusButtons.forEach((button) => (button.disabled = true));
  try {
    item = await api("PATCH", path, { status });
    render();
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    if (e instanceof ApiError && e.status === 404) {
      showMissing();
      return;
    }
    showError(itemError, describeError(e));
  } finally {
    statusButtons.forEach((button) => (button.disabled = false));
  }
}

async function changeCategory() {
  hideMessage(categoryError);
  categoryNote.textContent = "";
  const value = categorySelect.value;
  categorySelect.disabled = true;
  try {
    item = await api("PATCH", path, { category_id: value ? Number(value) : null });
    render();
    categoryNote.textContent = "Категория сохранена.";
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    if (e instanceof ApiError && e.status === 404) {
      // 404 бывает и у материала, и у категории: проверяем материал
      try {
        item = await api("GET", path);
      } catch (e2) {
        if (e2 instanceof ApiError && e2.status === 404) {
          showMissing();
          return;
        }
      }
      await loadCategories();
      render();
      showError(categoryError, "Такой категории больше нет. Список обновлён.");
    } else {
      showError(categoryError, describeError(e));
    }
    fillCategorySelect();
  } finally {
    categorySelect.disabled = false;
  }
}

async function removeItem() {
  hideMessage(itemError);
  try {
    await api("DELETE", path);
    location.replace("./");
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    if (e instanceof ApiError && e.status === 404) {
      location.replace("./"); // уже удалён
      return;
    }
    showError(itemError, describeError(e));
  }
}

function setupDelete() {
  const dialog = $("#delete-dialog");
  $("#delete").addEventListener("click", () => {
    $("#delete-text").textContent = `«${item.title}» будет удалён вместе с заметкой и напоминанием. Это нельзя отменить.`;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else if (window.confirm("Удалить материал? Это нельзя отменить.")) removeItem();
  });
  dialog.addEventListener("close", () => {
    const confirmed = dialog.returnValue === "confirm";
    dialog.returnValue = ""; // иначе Esc при следующем открытии сохранил бы прежнее значение
    if (confirmed) removeItem();
  });
}

function setupEdit() {
  onSubmit($("#edit-form"), async () => {
    hideMessage(editError);
    hideMessage(editInfo);
    const title = titleInput.value.trim();
    const note = noteInput.value.trim();
    if (!title) {
      showError(editError, "Название не может быть пустым.");
      titleInput.focus();
      return;
    }
    if (!note && !item.url) {
      showError(editError, "У заметки должен остаться текст. Чтобы убрать её, удалите материал.");
      noteInput.focus();
      return;
    }
    const changes = {};
    if (title !== item.title) changes.title = title;
    if (note !== (item.note ?? "")) changes.note = note;
    if (Object.keys(changes).length === 0) {
      showInfo(editInfo, "Изменений нет.");
      return;
    }
    try {
      item = await api("PATCH", path, changes);
      render();
      fillForm();
      showInfo(editInfo, "Изменения сохранены.");
    } catch (e) {
      if (redirectIfUnauthorized(e)) return;
      if (e instanceof ApiError && e.status === 404) {
        showMissing();
        return;
      }
      showError(
        editError,
        describeError(e, { 422: "Проверьте данные: название до 300 символов, заметка до 10 000." }),
      );
    }
  });
}

// ---------- напоминание ----------

function formatDateTime(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : dateTimeFormat.format(date);
}

// Значение для datetime-local строится из ЛОКАЛЬНЫХ частей даты:
// toISOString() даёт UTC и может сдвинуть день.
function toInputValue(date) {
  const pad = (number) => String(number).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

// Через N дней в ваше обычное время подборки (из настроек)
function presetDate(days) {
  const [hours, minutes] = (user.reminder_time ?? "09:00").split(":").map(Number);
  const date = new Date();
  date.setDate(date.getDate() + days);
  date.setHours(hours, minutes, 0, 0);
  return date;
}

function renderReminder() {
  reminderStatus.textContent = reminder
    ? `Напомним: ${formatDateTime(reminder.scheduled_at)}.`
    : "Напоминание не задано.";
  reminderClear.hidden = reminder === null;

  let hint = "";
  if (!user.email_verified_at) hint = "Письмо придёт только после подтверждения e-mail.";
  else if (!user.reminders_enabled) hint = "Напоминания отключены в настройках, письмо не придёт.";
  reminderHint.textContent = hint;
  reminderHint.hidden = !hint;
}

async function loadReminder() {
  try {
    reminder = await api("GET", reminderPath);
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    showError(reminderError, describeError(e));
  }
}

let reminderBusy = false;

async function saveReminder(date) {
  if (reminderBusy) return;
  hideMessage(reminderError);
  if (Number.isNaN(date.getTime())) {
    showError(reminderError, "Укажите дату и время.");
    return;
  }
  if (date.getTime() <= Date.now()) {
    showError(reminderError, "Время должно быть в будущем.");
    return;
  }
  reminderBusy = true;
  try {
    reminder = await api("PUT", reminderPath, { scheduled_at: date.toISOString() });
    renderReminder();
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    if (e instanceof ApiError && e.status === 404) {
      showMissing();
      return;
    }
    showError(
      reminderError,
      describeError(e, {
        409: "Не получилось сохранить: возможно, достигнут лимит в 100 напоминаний. Уберите лишние и повторите.",
        422: "Время должно быть в будущем и не дальше чем через год.",
      }),
    );
  } finally {
    reminderBusy = false;
  }
}

async function clearReminder() {
  if (reminderBusy) return;
  hideMessage(reminderError);
  reminderBusy = true;
  try {
    await api("DELETE", reminderPath);
    reminder = null;
    renderReminder();
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    if (e instanceof ApiError && e.status === 404) {
      showMissing();
      return;
    }
    showError(reminderError, describeError(e));
  } finally {
    reminderBusy = false;
  }
}

function setupReminder() {
  reminderInput.min = toInputValue(new Date());
  $("#preset-hint").textContent =
    `Быстрый выбор ставит время подборки из настроек (${user.reminder_time}) по часам вашего браузера.`;
  presetButtons.forEach((button) =>
    button.addEventListener("click", () => saveReminder(presetDate(Number(button.dataset.preset)))),
  );
  reminderClear.addEventListener("click", clearReminder);
  onSubmit($("#reminder-form"), async () => {
    await saveReminder(new Date(reminderInput.value));
  });
}

async function main() {
  user = await requireUser();
  initTopbar(user);
  $("#main").hidden = false;
  markReady();

  if (!/^[1-9]\d{0,18}$/.test(id)) {
    showMissing();
    return;
  }
  try {
    item = await api("GET", path);
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) {
      showMissing();
      return;
    }
    throw e;
  }
  await loadCategories();
  await loadReminder();
  render();
  fillForm();
  fillCategorySelect();
  renderReminder();
  setupReminder();
  $("#item").hidden = false;

  statusButtons.forEach((button) =>
    button.addEventListener("click", () => changeStatus(button.dataset.status)),
  );
  categorySelect.addEventListener("change", changeCategory);
  setupEdit();
  setupDelete();
  bindOpenTracking(document.body, refresh);
}

main().catch((error) => {
  markReady();
  showError($("#error"), describeError(error));
});