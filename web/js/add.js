import { api } from "./api.js";
import { redirectIfUnauthorized, requireUser } from "./session.js";
import {
  $, describeError, el, hideMessage, markReady, onSubmit, shorten, showError, showInfo,
} from "./ui.js";

// Ссылка и название приходят во фрагменте адреса (#url=...&title=...):
// фрагмент не уходит на сервер и не попадает в его журналы. Страница только
// заполняет форму, сохраняет человек кнопкой.
const params = new URLSearchParams(location.hash.slice(1));

const form = $("#add-form");
const error = $("#add-error");
const info = $("#add-info");

async function loadCategories() {
  try {
    const categories = await api("GET", "/categories");
    $("#add-category").append(
      ...categories.map((c) => el("option", { text: c.name, attrs: { value: String(c.id) } })),
    );
  } catch (e) {
    redirectIfUnauthorized(e);
    // без категорий форма работает
  }
}

onSubmit(form, async () => {
  hideMessage(error);
  hideMessage(info);
  const url = $("#add-url").value.trim();
  if (!url) {
    showError(error, "Введите ссылку.");
    $("#add-url").focus();
    return;
  }
  const body = { url };
  const title = $("#add-title").value.trim();
  const note = $("#add-note").value.trim();
  const category = $("#add-category").value;
  if (title) body.title = title;
  if (note) body.note = note;
  if (category) body.category_id = Number(category);
  showInfo(
    info,
    title ? "Сохраняю…" : "Сохраняю и загружаю название страницы. Это может занять несколько секунд.",
  );
  try {
    const saved = await api("POST", "/contents", body);
    form.hidden = true;
    showInfo(info, `Сохранено: ${saved.title}`);
    $("#open-saved").href = `item.html?id=${encodeURIComponent(String(saved.id))}`;
    $("#done").hidden = false;
  } catch (e) {
    if (redirectIfUnauthorized(e)) return;
    hideMessage(info);
    showError(
      error,
      describeError(e, {
        404: "Выбранной категории больше нет. Закройте окно и откройте закладку заново.",
        409: "Эта ссылка уже есть в вашей библиотеке.",
        422: "Не получилось сохранить: ссылка выглядит некорректно. Проверьте адрес.",
      }),
    );
  }
});

$("#close-window").addEventListener("click", () => {
  window.close();
  $("#close-hint").hidden = false; // если окно закрылось, подсказку никто не увидит
});

async function main() {
  await requireUser();
  $("#main").hidden = false;
  markReady();

  const url = (params.get("url") ?? "").trim();
  $("#add-url").value = url;
  $("#add-title").value = shorten((params.get("title") ?? "").trim(), 300);
  await loadCategories();
  // Ссылка уже есть: фокус на название, Enter сохраняет
  (url ? $("#add-title") : $("#add-url")).focus();
}

main().catch((error) => {
  markReady();
  showError($("#error"), describeError(error));
});