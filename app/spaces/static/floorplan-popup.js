// 樓層平面圖：點擊教室圓點 → 在圓點旁展開資訊卡（沒有 JS 時圓點本身就是教室頁連結）
(function () {
  'use strict';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;   // 一律用 textContent，避免 XSS
    return e;
  }

  function row(label, value) {
    var r = el('div', 'pp-row');
    r.appendChild(el('span', 'pp-label', label));
    r.appendChild(el('span', null, value));
    return r;
  }

  function buildCard(info, close) {
    var card = document.createDocumentFragment();
    var head = el('div', 'pp-head');
    var title = el('div');
    title.appendChild(el('strong', null, info.code));
    if (info.alias) title.appendChild(el('span', 'alias', info.alias));
    head.appendChild(title);
    var x = el('button', 'pp-close', '×');
    x.type = 'button';
    x.setAttribute('aria-label', '關閉');
    x.addEventListener('click', close);
    head.appendChild(x);
    card.appendChild(head);

    var tags = el('div', 'tags');
    tags.appendChild(el('span', 'tag cat-' + info.categoryKey, info.category));
    if (!info.bookable) tags.appendChild(el('span', 'tag gray', '不開放借用'));
    if (info.hasPanorama) tags.appendChild(el('span', 'tag dark', '360°'));
    card.appendChild(tags);

    var rows = el('div', 'pp-rows');
    rows.appendChild(row('類型', info.type || '—'));
    rows.appendChild(row('樓層', info.floor));
    rows.appendChild(row('人數', info.capacity + ' 人'));
    rows.appendChild(row('管理單位', info.manager || '未註明'));
    card.appendChild(rows);

    if (info.facilities && info.facilities.length) {
      var chips = el('div', 'chips');
      info.facilities.forEach(function (name) { chips.appendChild(el('span', 'chip', name)); });
      card.appendChild(chips);
    }
    var link = el('a', 'button pp-more', '查看教室詳情 →');
    link.href = info.url;
    card.appendChild(link);
    return card;
  }

  // stage＝外框 .plan-frame（不捲動）；平面圖在裡面的 .plan-wrap 捲動
  document.querySelectorAll('[data-plan]').forEach(function (stage) {
    var popup = stage.querySelector('.plan-popup');
    var dataEl = stage.querySelector('.plan-info');
    var scroller = stage.querySelector('.plan-wrap');
    if (!popup || !dataEl) return;
    var info = JSON.parse(dataEl.textContent || '{}');
    var active = null;

    function close() {
      popup.hidden = true;
      popup.replaceChildren();
      if (active) active.classList.remove('active');
      active = null;
    }

    function open(dot) {
      var data = info[dot.dataset.id];
      if (!data) return;
      if (active) active.classList.remove('active');
      active = dot;
      dot.classList.add('active');
      popup.replaceChildren(buildCard(data, close));
      popup.hidden = false;

      // 資訊卡放在圓點上方，放不下就放下方，並限制在平面圖範圍內
      var stageBox = stage.getBoundingClientRect();
      var dotBox = dot.getBoundingClientRect();
      var cx = dotBox.left + dotBox.width / 2 - stageBox.left;
      var cy = dotBox.top + dotBox.height / 2 - stageBox.top;
      var w = popup.offsetWidth, h = popup.offsetHeight, gap = 14;
      var left = Math.min(Math.max(cx - w / 2, 8), Math.max(8, stage.offsetWidth - w - 8));
      var top = cy - h - gap;
      if (top < 8) top = cy + gap;
      popup.style.left = left + 'px';
      popup.style.top = top + 'px';
      popup.querySelector('.pp-close').focus({ preventScroll: true });
    }

    stage.addEventListener('click', function (ev) {
      var dot = ev.target.closest('.room-dot');
      if (dot && stage.contains(dot)) {
        ev.preventDefault();
        if (dot === active) close(); else open(dot);
      }
    });
    document.addEventListener('click', function (ev) {
      if (!popup.hidden && !stage.contains(ev.target)) close();
    });
    // 左右捲動平面圖時圓點會移動，資訊卡位置就不準了，直接關閉
    if (scroller) scroller.addEventListener('scroll', function () { if (!popup.hidden) close(); });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && !popup.hidden) {
        var dot = active;
        close();
        if (dot) dot.focus();
      }
    });
  });
})();
