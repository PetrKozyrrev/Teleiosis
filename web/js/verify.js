import { api } from "./api.js";
import { $, describeError, hideMessage, onSubmit, showError, showInfo } from "./ui.js";

// Токен нужен только в памяти страницы: убираем его из адресной строки и истории
const token = new URLSearchParams(location.hash.slice(1)).get("token");
history.replaceState(null, "", location.pathname + location.search);

const form = $("#verify-form");
const error = $("#error");
const info = $("#info");
const toLibrary = $("#to-library");

if (!token) {
  form.hidden = true;
  toLibrary.hidden = false;
  showError(error, "В адресе нет ссылки подтверждения. Запросите новое письмо в библиотеке.");
}

// Подтверждаем только по нажатию кнопки: почтовые сканеры сами открывают ссылки
onSubmit(form, async () => {
  hideMessage(error);
  try {
    await api("POST", "/auth/email-verification/confirm", { token });
    form.hidden = true;
    toLibrary.hidden = false;
    showInfo(info, "Адрес подтверждён. Спасибо!");
  } catch (e) {
    toLibrary.hidden = false;
    showError(
      error,
      describeError(e, { 400: "Ссылка недействительна или устарела. Запросите новое письмо в библиотеке." }),
    );
  }
});