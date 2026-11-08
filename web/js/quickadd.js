import { api } from "./api.js";
import { redirectIfUnauthorized } from "./session.js";
import { $, describeError, hideMessage, onSubmit, showError, showInfo } from "./ui.js";

// Адрес с http(s):// или вида example.com/путь (латиница, без пробелов)
const URL_PATTERN = /^(?:https?:\/\/\S+|(?:[\w-]+\.)+[a-z]{2,}(?::\d+)?(?:[/?#]\S*)?)$/i;

// Первое слово похоже на ссылку: ссылка, остальное заметка. Иначе вся строка заметка.
export function parseInput(text) {
  const value = text.trim();
  const match = value.match(/^(\S+)(?:\s+([\s\S]*))?$/);
  if (match && URL_PATTERN.test(match[1])) {
    const note = (match[2] ?? "").trim();
    return note ? { url: match[1], note } : { url: match[1] };
  }
  return { note: value };
}

export function initQuickAdd({ onSaved }) {
  const form = $("#add-form");
  const input = $("#add-input");
  const error = $("#add-error");
  const info = $("#add-info");

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  onSubmit(form, async () => {
    hideMessage(error);
    hideMessage(info);
    if (!input.value.trim()) {
      showError(error, "Введите ссылку или текст заметки.");
      return;
    }
    const body = parseInput(input.value);
    if (body.url) {
      showInfo(info, "Сохраняю и загружаю название страницы. Это может занять несколько секунд.");
    }
    try {
      const saved = await api("POST", "/contents", body);
      input.value = "";
      showInfo(info, `Сохранено: ${saved.title}`);
      await onSaved();
    } catch (e) {
      if (redirectIfUnauthorized(e)) return;
      hideMessage(info);
      showError(
        error,
        describeError(e, {
          409: "Эта ссылка уже есть в вашей библиотеке.",
          422: body.url
            ? "Не получилось сохранить: ссылка выглядит некорректно. Проверьте адрес."
            : "Заметка пустая или длиннее 10 000 символов.",
        }),
      );
    }
  });
}