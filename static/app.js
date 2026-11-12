(function () {
  "use strict";

  // Подтверждение опасных действий (удаление склада, отправка, отмена).
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm || "Продолжить?")) {
        event.preventDefault();
      }
    });
  });

  // Закрытие уведомлений.
  document.querySelectorAll(".flash-close").forEach(function (button) {
    button.addEventListener("click", function () {
      var flash = button.closest(".flash");
      if (flash) {
        flash.remove();
      }
    });
  });

  // Уведомление исчезает само, но не мешает читать длинный текст.
  document.querySelectorAll(".flash-ok").forEach(function (flash) {
    window.setTimeout(function () {
      flash.style.transition = "opacity .4s ease, transform .4s ease";
      flash.style.opacity = "0";
      flash.style.transform = "translateY(-4px)";
      window.setTimeout(function () {
        flash.remove();
      }, 420);
    }, 8000);
  });
})();
