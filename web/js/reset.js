import { api, ApiError } from "./api.js";
import {
  $, attachPasswordToggle, describeError, hideMessage, onSubmit, passwordProblem, showError, showInfo,
} from "./ui.js";

// Токен нужен только в памяти страницы: убираем его из адресной строки и истории
const token = new URLSearchParams(location.hash.slice(1)).get("token");
history.replaceState(null, "", location.pathname + location.search);

const form = $("#reset-form");
const error = $("#error");
const info = $("#info");
const toForgot = $("#to-forgot");
attachPasswordToggle($("#toggle-password"), $("#password"));

if (!token) {
  form.hidden = true;
  toForgot.hidden = false;
  showError(error, "В адресе нет ссылки для сброса. Запросите новую ссылку.");
}

onSubmit(form, async () => {
  hideMessage(error);
  const password = $("#password").value;
  const problem = passwordProblem(password);
  if (problem) {
    showError(error, problem);
    $("#password").focus();
    return;
  }
  try {
    await api("POST", "/auth/password-reset/confirm", { token, password });
    form.hidden = true;
    showInfo(info, "Пароль изменён. Теперь войдите с новым паролем.");
  } catch (e) {
    if (e instanceof ApiError && e.status === 400) toForgot.hidden = false;
    showError(error, describeError(e, { 400: "Ссылка недействительна или устарела. Запросите новую." }));
  }
});