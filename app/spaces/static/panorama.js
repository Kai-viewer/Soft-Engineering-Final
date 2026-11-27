// 360° 全景照片：Pannellum（https://pannellum.org/）
(function () {
  'use strict';
  var el = document.getElementById('panorama');
  if (!el) return;
  if (!window.pannellum) {
    el.className = 'pano-empty';
    el.textContent = '無法載入全景元件（Pannellum 需要網路連線）';
    return;
  }
  pannellum.viewer('panorama', {
    type: 'equirectangular',
    panorama: el.dataset.src,
    title: el.dataset.title,
    autoLoad: true,
    autoRotate: -2,
    showFullscreenCtrl: true,
    hfov: 100
  });
})();
