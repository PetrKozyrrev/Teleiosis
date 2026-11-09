// Запасной сигнал: если скрипт страницы не запустился (ошибка в коде или файле),
// пользователь увидит сообщение, а не пустой экран.
// Страница отмечает успешный запуск вызовом markReady() из ui.js.
(function () {
  setTimeout(function () {
    if (document.documentElement.dataset.ready) return;
    var box = document.getElementById("boot-error");
    if (!box) return;
    box.textContent = "Страница не загрузилась полностью. Обновите её (Ctrl+R). Если не помогает, попробуйте позже.";
    box.hidden = false;
  }, 8000);
})();