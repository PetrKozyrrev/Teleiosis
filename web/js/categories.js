import { api, ApiError } from "./api.js";
import { initTopbar, redirectIfUnauthorized, requireUser } from "./session.js";
import { $, describeError, el, hideMessage, markReady, onSubmit, showError, showInfo } from "./ui.js";

const DUPLICATE = "Такая категория уже есть. Регистр букв не важен.";
const LENGTH = "Название должно быть от 1 до 50 символов.";

const state = { categories: [], editing: null, pendingDelete: null };
const list = $("#categories");
const listError = $("#list-error");
const retry = $("#retry");
const createError = $("#create-error");
const createInfo = $("#create-info");
const nameInput = $("#new-name");
const dialog = $("#delete-dialog");

function materials(count) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  let word = "материалов";
  if (mod10 === 1 && mod100 !== 11) word = "материал";
  else if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) word = "материала";
  return `${count} ${word}`;
}

const categoryPath = (category) => `/categories/${encodeURIComponent(category.id)}`;

function renderEditRow(category) {
  const input = el("input", {
    class: "input rename-input",
    attrs: {
      type: "text",
      maxlength: "50",
      required: "",
      autocomplete: "off",
      "aria-label": "Новое название категории",
    },
  });
  input.value = category.name;
  const cancel = el("button", { class: "button-quiet", text: "Отмена", attrs: { type: "button" } });
  cancel.addEventListener("click", () => {
    state.editing = null;
    hideMessage(listError);
    render();
  });
  const form = el(
    "form",
    { class: "rename-form", attrs: { method: "post" } },
    input,
    el("button", { class: "button button-inline", text: "Сохранить", attrs: { type: "submit" } }),
    cancel,
  );
  onSubmit(form, () => rename(category, input.value));
  return el("li", { class: "item category-row" }, form);
}

function renderRow(category) {
  if (state.editing === category.id) return renderEditRow(category);

  const actions = el("div", { class: "category-actions" });
  if (category.contents_count > 0) {
    actions.append(
      el("a", {
        text: "Показать материалы",
        attrs: { href: `./?category=${encodeURIComponent(String(category.id))}` },
      }),
    );
  }
  const renameButton = el("button", {
    class: "button-quiet",
    text: "Переименовать",
    attrs: { type: "button", "aria-label": `Переименовать категорию «${category.name}»` },
  });
  renameButton.addEventListener("click", () => {
    state.editing = category.id;
    hideMessage(listError);
    render();
  });
  const removeButton = el("button", {
    class: "button-quiet button-danger-quiet",
    text: "Удалить",
    attrs: { type: "button", "aria-label": `Удалить категорию «${category.name}»` },
  });
  removeButton.addEventListener("click", () => askDelete(category));
  actions.append(renameButton, removeButton);

  return el(
    "li",
    { class: "item category-row" },
    el(
      "div",
      { class: "category-main" },
      el("h3", { class: "item-title", text: category.name }),
      el("p", { class: "hint", text: materials(category.contents_count) }),
    ),
    actions,
  );
}

function render() {
  list.replaceChildren(...state.categories.map(renderRow));
  $("#empty").hidden = state.categories.length > 0 || !listError.hidden;
  $("#count").textContent = state.categories.length ? `Категорий: ${state.categories.length}` : "";
  retry.hidden = listError.hidden;
  const input = list.querySelector(".rename-input");
  if (input) {
    input.focus();
    input.select();
  }
}

async function load() {
  hideMessage(listError);
  try {
    state.categories = await api("GET", "/categories");
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    showError(listError, describeError(e));
  }
  render();
}

// Общая обработка ошибок изменений. 404: категорию уже удалили в другом окне.
async function failed(error, overrides = {}) {
  if (redirectIfUnauthorized(error)) return;
  if (error instanceof ApiError && error.status === 404) {
    state.editing = null;
    await load();
    showError(listError, "Такой категории больше нет. Список обновлён.");
    render();
    return;
  }
  showError(listError, describeError(error, overrides));
}

async function rename(category, value) {
  hideMessage(listError);
  const name = value.trim();
  if (!name) {
    showError(listError, "Название не может быть пустым.");
    return;
  }
  if (name === category.name) {
    state.editing = null;
    render();
    return;
  }
  try {
    await api("PATCH", categoryPath(category), { name });
    state.editing = null;
    await load();
  } catch (e) {
    await failed(e, { 409: DUPLICATE, 422: LENGTH });
  }
}

function askDelete(category) {
  state.pendingDelete = category;
  const count = category.contents_count;
  $("#delete-text").textContent =
    count > 0
      ? `Категория «${category.name}» будет удалена. Материалы (${count}) останутся в библиотеке без категории.`
      : `Категория «${category.name}» будет удалена.`;
  if (typeof dialog.showModal === "function") dialog.showModal();
  else if (window.confirm(`Удалить категорию «${category.name}»?`)) removeCategory();
}

async function removeCategory() {
  const category = state.pendingDelete;
  state.pendingDelete = null;
  if (!category) return;
  hideMessage(listError);
  try {
    await api("DELETE", categoryPath(category));
    await load();
  } catch (e) {
    await failed(e);
  }
}

dialog.addEventListener("close", () => {
  const confirmed = dialog.returnValue === "confirm";
  dialog.returnValue = ""; // иначе Esc при следующем открытии сохранил бы прежнее значение
  if (confirmed) removeCategory();
});

onSubmit($("#create-form"), async () => {
  hideMessage(createError);
  hideMessage(createInfo);
  const name = nameInput.value.trim();
  if (!name) {
    showError(createError, "Введите название категории.");
    nameInput.focus();
    return;
  }
  try {
    await api("POST", "/categories", { name });
    nameInput.value = "";
    showInfo(createInfo, `Категория создана: ${name}`);
    await load();
    nameInput.focus();
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    showError(createError, describeError(e, { 409: DUPLICATE, 422: LENGTH }));
  }
});

async function main() {
  const user = await requireUser();
  initTopbar(user);
  $("#main").hidden = false;
  markReady();
  retry.addEventListener("click", load);
  await load();
}

main().catch((error) => {
  markReady();
  showError($("#error"), describeError(error));
});