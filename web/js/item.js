import { api, ApiError } from "./api.js";
import { SOURCE_LABELS, bindOpenTracking, formatDate, hostOf } from "./cards.js";
import { initTopbar, redirectIfUnauthorized, requireUser } from "./session.js";
import {
  $, describeError, el, hideMessage, markReady, onSubmit, safeHttpUrl, showError, showInfo,
} from "./ui.js";

const id = new URLSearchParams(location.search).get("id") ?? "";
const path = `/contents/${encodeURIComponent(id)}`;
let item = null;
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
    $("#delete-text").textContent = `«${item.title}» будет удалён вместе с заметкой. Это нельзя отменить.`;
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

async function main() {
  const user = await requireUser();
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
  render();
  fillForm();
  fillCategorySelect();
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