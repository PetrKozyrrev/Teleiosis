import { api } from "./api.js";
import { $, describeError, hideMessage, onSubmit, showError, showInfo } from "./ui.js";

const form = $("#forgot-form");
const error = $("#error");
const info = $("#info");

onSubmit(form, async () => {
  hideMessage(error);
  try {
    await api("POST", "/auth/password-reset/request", { email: $("#email").value.trim() });
    form.hidden = true;
    $("#lead").hidden = true;
    showInfo(info, "Если такой аккаунт есть, письмо уже отправлено. Ссылка действует 1 час.");
  } catch (e) {
    showError(error, describeError(e, { 422: "Проверьте адрес e-mail." }));
  }
});