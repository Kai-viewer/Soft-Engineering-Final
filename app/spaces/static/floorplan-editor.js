// 管理員：選教室 → 在平面圖上點擊位置 → 送出表單儲存（座標為 0～100 的百分比，對應 rooms.map_x / map_y）
(function () {
  'use strict';
  var svg = document.getElementById('floorplan-svg');
  var select = document.getElementById('pos-room');
  var form = document.getElementById('pos-form');
  if (!svg || !select || !form) return;
  var viewBox = svg.viewBox.baseVal;

  function highlightSelected() {
    svg.querySelectorAll('.room-dot').forEach(function (g) {
      g.classList.toggle('selected', g.dataset.id === select.value);
    });
  }

  svg.addEventListener('click', function (ev) {
    var dot = ev.target.closest('.room-dot');
    if (dot && !ev.shiftKey) {           // 點到既有圓點：選取該教室
      select.value = dot.dataset.id;
      highlightSelected();
      return;
    }
    if (!select.value) return;
    var pt = svg.createSVGPoint();
    pt.x = ev.clientX;
    pt.y = ev.clientY;
    var p = pt.matrixTransform(svg.getScreenCTM().inverse());
    var pct = function (v, size) { return Math.min(100, Math.max(0, v / size * 100)).toFixed(2); };
    document.getElementById('pos-x').value = pct(p.x, viewBox.width);
    document.getElementById('pos-y').value = pct(p.y, viewBox.height);
    form.submit();
  });

  select.addEventListener('change', highlightSelected);
  if (select.dataset.selected) select.value = select.dataset.selected;
  highlightSelected();
})();
