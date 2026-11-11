import { api } from "./api.js";
import { $, describeError, hideMessage, onSubmit, showError, showInfo } from "./ui.js";

// Токен нужен только в памяти страницы: убираем его из адресной строки и истории
const token = new URLSearchParams(location.hash.slice(1)).get("token");
history.replaceState(null, "", location.pathname + location.search);

const form = $("#unsubscribe-form");
const error = $("#error");
const info = $("#info");

if (!token) {
  form.hidden = true;
  showError(error, "В адресе нет ссылки отписки. Напоминания можно отключить в настройках.");
  $("#to-settings").hidden = false;
}

// Отписываем только по нажатию кнопки: почтовые сканеры сами открывают ссылки
onSubmit(form, async () => {
  hideMessage(error);
  try {
    await api("POST", "/auth/unsubscribe", { token });
    form.hidden = true;
    showInfo(info, "Готово: напоминания отключены.");
    $("#to-settings").hidden = false;
  } catch (e) {
    $("#to-settings").hidden = false;
    showError(
      error,
      describeError(e, {
        400: "Ссылка недействительна. Отключить напоминания можно в настройках.",
      }),
    );
  }
});