/* 홈 오른쪽 그림: 고분자 그물(정지 이미지) 위로 민트색 이온이 곡선을 따라 흐른다.
   이미지 속 실제 경로는 추적할 수 없어서, 그림에 보이는 이온 무리와 사슬을 잇는 곡선을
   손으로 정했다(좌표는 그림 크기에 대한 비율 0–1). 움직임 줄이기 설정이면 멈춘 한 장면만 그린다. */
(function () {
  "use strict";
  var art = document.querySelector(".hero-art");
  if (!art) return;
  var canvas = art.querySelector("canvas");
  var img = art.querySelector("img");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");

  // 이온이 지나가는 곡선(점들을 Catmull-Rom 곡선으로 잇는다)
  var PATHS = [
    [[0.25, 0.34], [0.33, 0.30], [0.43, 0.28], [0.52, 0.30], [0.61, 0.33], [0.68, 0.36], [0.74, 0.43], [0.79, 0.50]],
    [[0.22, 0.58], [0.30, 0.57], [0.35, 0.57], [0.44, 0.61], [0.52, 0.56], [0.59, 0.51], [0.69, 0.48], [0.79, 0.50]],
    [[0.55, 0.22], [0.52, 0.30], [0.54, 0.41], [0.59, 0.51], [0.61, 0.60], [0.61, 0.69], [0.57, 0.77]],
    [[0.18, 0.45], [0.22, 0.58], [0.29, 0.67], [0.38, 0.69], [0.44, 0.61]],
    [[0.68, 0.36], [0.73, 0.47], [0.72, 0.58], [0.66, 0.66], [0.61, 0.69], [0.51, 0.74], [0.41, 0.79]],
    [[0.30, 0.43], [0.39, 0.46], [0.47, 0.47], [0.54, 0.42], [0.59, 0.51], [0.67, 0.58], [0.76, 0.62]],
    [[0.79, 0.50], [0.82, 0.40], [0.76, 0.30], [0.68, 0.27], [0.61, 0.33]],
    [[0.44, 0.61], [0.47, 0.70], [0.55, 0.74], [0.61, 0.69]]
  ];

  // 곡선을 촘촘한 점 목록으로 바꿔 두고, 길이 기준으로 위치를 찾는다
  function sample(pts) {
    var out = [], n = pts.length;
    for (var i = 0; i < n - 1; i++) {
      var p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(n - 1, i + 2)];
      for (var k = 0; k < 24; k++) {
        var t = k / 24, t2 = t * t, t3 = t2 * t;
        out.push([
          0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
          0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
        ]);
      }
    }
    out.push(pts[n - 1]);
    var len = [0];
    for (var j = 1; j < out.length; j++) len.push(len[j - 1] + Math.hypot(out[j][0] - out[j - 1][0], out[j][1] - out[j - 1][1]));
    return { pts: out, len: len, total: len[len.length - 1] };
  }
  var CURVES = PATHS.map(sample);

  function at(c, u) {
    var d = u * c.total, lo = 0, hi = c.len.length - 1;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (c.len[mid] < d) lo = mid; else hi = mid; }
    var seg = c.len[hi] - c.len[lo] || 1, f = (d - c.len[lo]) / seg;
    var a = c.pts[lo], b = c.pts[hi];
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, b[0] - a[0], b[1] - a[1]];
  }

  // 빛나는 이온 하나를 미리 그려 두고 복사해 쓴다(매 프레임 그림자 계산을 피함)
  var SPRITE = 64;
  var sprite = document.createElement("canvas");
  sprite.width = sprite.height = SPRITE;
  (function () {
    var s = sprite.getContext("2d"), r = SPRITE / 2;
    var g = s.createRadialGradient(r, r, 0, r, r, r);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.12, "rgba(120,240,205,1)");
    g.addColorStop(0.3, "rgba(40,200,165,0.55)");
    g.addColorStop(0.6, "rgba(40,200,165,0.14)");
    g.addColorStop(1, "rgba(40,200,165,0)");
    s.fillStyle = g;
    s.fillRect(0, 0, SPRITE, SPRITE);
  })();

  var W = 0, H = 0, DPR = 1, parts = [];
  var small = window.matchMedia("(max-width: 720px)");

  function makePart(i, spread) {
    return {
      c: CURVES[i % CURVES.length],
      u: spread ? Math.random() : 0,
      v: 0.035 + Math.random() * 0.035,      // 곡선 길이 비율/초: 한 바퀴 15–30초
      r: 0.55 + Math.random() * 0.6,         // 크기 배율
      ph: Math.random() * Math.PI * 2,       // 옆으로 흔들리는 위상
      prev: null
    };
  }
  function seed() {
    var n = small.matches ? 12 : 22;
    parts = [];
    for (var i = 0; i < n; i++) parts.push(makePart(i, true));
  }

  function resize() {
    // clientWidth는 CSS 확대(transform) 전 크기라 그림과 같은 좌표계를 쓴다
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = Math.max(1, canvas.clientWidth);
    H = Math.max(1, canvas.clientHeight);
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    parts.forEach(function (p) { p.prev = null; });
  }

  function pos(p, time) {
    var q = at(p.c, p.u);
    var nl = Math.hypot(q[2], q[3]) || 1;
    var wob = Math.sin(time * 0.9 + p.ph) * 0.006;   // 사슬 안에서 살짝 흔들림
    return [(q[0] - q[3] / nl * wob) * W, (q[1] + q[2] / nl * wob) * H];
  }

  function drawIon(x, y, p, alpha) {
    var s = Math.max(W, H) / 330 * 15 * p.r;
    ctx.globalAlpha = alpha;
    ctx.drawImage(sprite, x - s / 2, y - s / 2, s, s);
  }

  var running = false, last = 0, visible = true, raf = 0;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");

  function frame(now) {
    raf = 0;
    if (!running) return;
    var dt = last ? Math.min((now - last) / 1000, 0.05) : 0.016;
    last = now;
    var t = now / 1000;
    // 꼬리: 이전 그림을 조금씩 지운다(프레임 속도와 무관하게 같은 속도로)
    ctx.globalCompositeOperation = "destination-out";
    ctx.globalAlpha = 1 - Math.pow(0.93, dt * 60);
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = "source-over";
    ctx.lineCap = "round";
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i];
      p.u += p.v * dt;
      if (p.u >= 1) { parts[i] = p = makePart(Math.floor(Math.random() * CURVES.length), false); }
      var a = Math.sin(Math.PI * p.u);                // 곡선 양 끝에서 서서히 나타나고 사라진다
      var xy = pos(p, t);
      if (p.prev) {
        ctx.globalAlpha = 0.5 * a;
        ctx.strokeStyle = "rgba(40,190,160,1)";
        ctx.lineWidth = Math.max(1, W / 330 * 1.6 * p.r);
        ctx.beginPath();
        ctx.moveTo(p.prev[0], p.prev[1]);
        ctx.lineTo(xy[0], xy[1]);
        ctx.stroke();
      }
      drawIon(xy[0], xy[1], p, 0.9 * a);
      p.prev = xy;
    }
    ctx.globalAlpha = 1;
    raf = requestAnimationFrame(frame);
  }

  function drawStill() {
    ctx.clearRect(0, 0, W, H);
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i];
      drawIon.apply(null, pos(p, 0).concat([p, 0.85 * Math.sin(Math.PI * Math.max(0.15, Math.min(0.85, p.u)))]));
    }
    ctx.globalAlpha = 1;
  }

  function update() {
    var go = !reduce.matches && visible && !document.hidden;
    if (go && !running) { running = true; last = 0; if (!raf) raf = requestAnimationFrame(frame); }
    else if (!go && running) { running = false; if (raf) cancelAnimationFrame(raf); raf = 0; }
    if (reduce.matches) drawStill();
  }

  function start() {
    seed();
    resize();
    update();
  }

  if ("ResizeObserver" in window) new ResizeObserver(function () { resize(); if (reduce.matches) drawStill(); }).observe(canvas);
  else window.addEventListener("resize", function () { resize(); if (reduce.matches) drawStill(); });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (es) { visible = es[0].isIntersecting; update(); }).observe(art);
  }
  document.addEventListener("visibilitychange", update);
  var onChange = function () { if (reduce.matches) { running = false; if (raf) cancelAnimationFrame(raf); raf = 0; } update(); };
  if (reduce.addEventListener) reduce.addEventListener("change", onChange); else if (reduce.addListener) reduce.addListener(onChange);
  if (small.addEventListener) small.addEventListener("change", function () { seed(); resize(); });

  if (img && !img.complete) img.addEventListener("load", start, { once: true });
  else start();
})();
