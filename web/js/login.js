import { api } from "./api.js";
import { redirectIfSignedIn } from "./session.js";
import { $, attachPasswordToggle, describeError, hideMessage, onSubmit, showError } from "./ui.js";

redirectIfSignedIn();

const form = $("#login-form");
const error = $("#error");
attachPasswordToggle($("#toggle-password"), $("#password"));

onSubmit(form, async () => {
  hideMessage(error);
  try {
    await api("POST", "/auth/login", {
      email: $("#email").value.trim(),
      password: $("#password").value,
    });
    location.replace("./");
  } catch (e) {
    showError(error, describeError(e, { 401: "Неверный e-mail или пароль." }));
    $("#password").focus();
  }
});