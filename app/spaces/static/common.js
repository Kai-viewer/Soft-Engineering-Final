// 空間查詢模組共用的小功能
(function () {
  'use strict';

  // 篩選表單：下拉選單 / 勾選框改變時自動送出
  document.querySelectorAll('[data-autosubmit]').forEach(function (el) {
    el.addEventListener('change', function () { el.form.submit(); });
  });

  // 刪除等危險操作：送出前確認
  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (ev) {
      if (!window.confirm(form.dataset.confirm)) ev.preventDefault();
    });
  });

  // 上傳前先檢查檔案大小
  document.querySelectorAll('input[type=file][data-max-mb]').forEach(function (input) {
    input.addEventListener('change', function () {
      var file = input.files[0];
      if (file && file.size > Number(input.dataset.maxMb) * 1024 * 1024) {
        alert('檔案太大，上限 ' + input.dataset.maxMb + 'MB');
        input.value = '';
      }
    });
  });
})();
