/* 홈 첫 화면 오른쪽 그림 (2026-11-04): 펄스가 이온 그물에 퍼졌다가 잦아든다. 설명용 모형, 실측 아님.
   - 노드: 고르게 흩뿌린 점(고정 씨앗), 선: 가까운 이웃 3–4개
   - 활성 a: 50 ms마다 a ← 0.8·a + 0.1·(이웃 중 가장 큰 a). 1초 뒤 약 절반, 2초 뒤 약 1할로 잦아든다
   - 부드럽게 보이도록(2026-11-04 수정): 계산은 50 ms마다 하되 화면은 매 프레임 두 계산 사이를 이어 그리고,
     누른 자리의 고리·떠도는 이온은 프레임 수가 아니라 흐른 시간(ms)으로 움직인다.
     선·점은 색 단계별로 묶어 한 번에 그려 프레임이 밀리지 않게 한다.
   - 아무도 누르지 않으면 3.5초마다 '한 번'과 '빠르게 두 번'을 번갈아 보여 준다.
     움직임 줄이기 설정이면 자동 재생 없이 한 장면만 그리고, 누를 때만 잠시 움직인다. */
(function () {
  "use strict";
  var fig = document.querySelector(".hh-art");
  if (!fig) return;
  var net = fig.querySelector(".hh-net");
  if (!net || !net.getContext) return;
  var ctx = net.getContext("2d");
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var STEP = 50, RING_MS = 1100, LEVELS = 10;
  var W = 0, H = 0, DPR = 1;
  var nodes = [], edges = [], nbr = [], act, prev, view, ions = [], rings = [], queue = [], shot = 0;
  var running = false, visible = true, raf = 0, lastT = 0, acc = 0, lastAuto = 0, autoPair = true, touched = -1e9;
  var glow = makeGlow();

  function rng(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  // 빛나는 점은 미리 그린 흐린 원 한 장을 크기만 바꿔 찍는다(매번 그라데이션을 만들지 않게)
  function makeGlow() {
    var c = document.createElement("canvas"), s = 64;
    c.width = c.height = s;
    var g = c.getContext("2d"), gr = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
    gr.addColorStop(0, "rgba(91,134,229,0.55)");
    gr.addColorStop(0.45, "rgba(91,134,229,0.22)");
    gr.addColorStop(1, "rgba(91,134,229,0)");
    g.fillStyle = gr; g.fillRect(0, 0, s, s);
    return c;
  }

  function build() {
    var r = fig.getBoundingClientRect();
    W = Math.max(1, Math.round(r.width)); H = Math.max(1, Math.round(r.height));
    DPR = Math.min(2, window.devicePixelRatio || 1);
    net.width = Math.round(W * DPR); net.height = Math.round(H * DPR);
    net.style.width = W + "px"; net.style.height = H + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

    var rand = rng(20261104), gap = W < 560 ? 34 : 42;
    nodes = [];
    for (var y = -gap / 2; y < H + gap; y += gap * 0.87) {
      for (var x = -gap / 2; x < W + gap; x += gap) {
        nodes.push({ x: x + (rand() - 0.5) * gap * 0.9, y: y + (rand() - 0.5) * gap * 0.9 });
      }
    }
    var n = nodes.length, seen = {};
    edges = []; nbr = [];
    for (var i = 0; i < n; i++) nbr.push([]);
    for (i = 0; i < n; i++) {
      var d = [];
      for (var j = 0; j < n; j++) {
        if (i === j) continue;
        var dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y;
        d.push([dx * dx + dy * dy, j]);
      }
      d.sort(function (a, b) { return a[0] - b[0]; });
      for (var k = 0; k < 4; k++) {
        var jj = d[k][1], key = i < jj ? i + "-" + jj : jj + "-" + i;
        if (k === 3 && rand() < 0.5) continue;
        if (seen[key]) continue;
        seen[key] = 1; edges.push([i, jj]); nbr[i].push(jj); nbr[jj].push(i);
      }
    }
    ions = [];
    var count = Math.round((W * H) / 30000);
    for (i = 0; i < count; i++) {
      var a0 = Math.floor(rand() * n);
      ions.push({ a: a0, b: nbr[a0][0], t: rand(), v: 0.00024 + rand() * 0.0003 }); // 1 ms에 가는 몫
    }
    act = new Float32Array(n); prev = new Float32Array(n); view = new Float32Array(n);
    rings = []; queue = [];
  }

  function nearest(x, y) {
    var best = 0, bd = 1e18;
    for (var i = 0; i < nodes.length; i++) {
      var dx = nodes[i].x - x, dy = nodes[i].y - y, dd = dx * dx + dy * dy;
      if (dd < bd) { bd = dd; best = i; }
    }
    return best;
  }
  // 펄스는 왼쪽(입력 쪽)에서 들어온다. 차례마다 조금씩 다른 자리
  function entry(k) {
    var ys = [0.5, 0.42, 0.58, 0.46, 0.54];
    return nearest(W * 0.18, H * ys[k % ys.length]);
  }
  function pulse(i, x, y, now) {
    act[i] = Math.min(1, act[i] + 1);
    for (var k = 0; k < nbr[i].length; k++) act[nbr[i][k]] = Math.min(1, act[nbr[i][k]] + 0.8);
    rings.push({ x: x == null ? nodes[i].x : x, y: y == null ? nodes[i].y : y, t0: now });
  }
  function fire(n, now) {
    pulse(entry(shot++), null, null, now);
    if (n === 2) queue.push(now + 350);
  }
  function step() {
    var n = nodes.length, next = prev; // 배열 두 개를 번갈아 쓴다
    for (var i = 0; i < n; i++) {
      var m = 0, nb = nbr[i];
      for (var k = 0; k < nb.length; k++) if (act[nb[k]] > m) m = act[nb[k]];
      var v = 0.8 * act[i] + 0.1 * m;
      next[i] = v < 0.004 ? 0 : v > 1 ? 1 : v;
    }
    prev = act; act = next;
  }

  function easeOut(p) { return 1 - Math.pow(1 - p, 3); }

  function draw(now, frac) {
    var i, n = nodes.length, a, b, s, lv;
    for (i = 0; i < n; i++) view[i] = prev[i] + (act[i] - prev[i]) * frac;
    ctx.clearRect(0, 0, W, H);

    // 선: 쉬는 선은 한 번에, 켜진 선은 밝기 단계별로 묶어서
    var buckets = [];
    for (lv = 0; lv <= LEVELS; lv++) buckets.push([]);
    for (i = 0; i < edges.length; i++) {
      s = Math.max(view[edges[i][0]], view[edges[i][1]]);
      buckets[s < 0.02 ? 0 : Math.max(1, Math.round(s * LEVELS))].push(edges[i]);
    }
    ctx.lineWidth = 1;
    for (lv = 0; lv <= LEVELS; lv++) {
      var bk = buckets[lv];
      if (!bk.length) continue;
      ctx.strokeStyle = "rgba(43,89,195," + (0.18 + 0.6 * (lv / LEVELS)).toFixed(3) + ")";
      ctx.beginPath();
      for (var e = 0; e < bk.length; e++) {
        a = nodes[bk[e][0]]; b = nodes[bk[e][1]];
        ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      }
      ctx.stroke();
    }

    // 켜진 노드의 빛
    for (i = 0; i < n; i++) {
      s = view[i];
      if (s < 0.03) continue;
      var gs = 10 + 26 * s;
      ctx.globalAlpha = Math.min(1, 0.25 + s);
      ctx.drawImage(glow, nodes[i].x - gs / 2, nodes[i].y - gs / 2, gs, gs);
    }
    ctx.globalAlpha = 1;
    // 점: 쉬는 점은 한 번에
    ctx.fillStyle = "rgba(30,66,159,0.5)";
    ctx.beginPath();
    for (i = 0; i < n; i++) {
      if (view[i] >= 0.03) continue;
      a = nodes[i]; ctx.moveTo(a.x + 1.6, a.y); ctx.arc(a.x, a.y, 1.6, 0, 6.2832);
    }
    ctx.fill();
    ctx.fillStyle = "rgb(30,66,159)";
    for (i = 0; i < n; i++) {
      s = view[i];
      if (s < 0.03) continue;
      a = nodes[i];
      ctx.globalAlpha = 0.5 + 0.5 * s;
      ctx.beginPath(); ctx.arc(a.x, a.y, 1.6 + 1.8 * s, 0, 6.2832); ctx.fill();
    }
    ctx.globalAlpha = 1;

    // 누른 자리의 고리: 시간에 따라 천천히 퍼지며 옅어진다(두 겹)
    for (i = rings.length - 1; i >= 0; i--) {
      var rg = rings[i];
      for (var k = 0; k < 2; k++) {
        var p = (now - rg.t0 - k * 180) / RING_MS;
        if (p <= 0 || p >= 1) continue;
        var q = easeOut(p);
        ctx.strokeStyle = "rgba(43,89,195," + (0.75 * Math.pow(1 - p, 1.6) * (k ? 0.55 : 1)).toFixed(3) + ")";
        ctx.lineWidth = 2.2 - 1.4 * p;
        ctx.beginPath(); ctx.arc(rg.x, rg.y, 4 + 58 * q, 0, 6.2832); ctx.stroke();
      }
      if (now - rg.t0 > RING_MS + 200) rings.splice(i, 1);
    }

    // 떠도는 이온
    ctx.fillStyle = "#fff"; ctx.strokeStyle = "rgba(43,89,195,0.85)"; ctx.lineWidth = 1.2;
    ctx.beginPath();
    for (i = 0; i < ions.length; i++) {
      var o = ions[i]; a = nodes[o.a]; b = nodes[o.b];
      var x = a.x + (b.x - a.x) * o.t, y = a.y + (b.y - a.y) * o.t;
      ctx.moveTo(x + 2.4, y); ctx.arc(x, y, 2.4, 0, 6.2832);
    }
    ctx.fill(); ctx.stroke();
  }

  function moveIons(dt) {
    for (var i = 0; i < ions.length; i++) {
      var o = ions[i];
      o.t += o.v * dt * (1 + 2.5 * Math.max(view[o.a], view[o.b]));
      while (o.t >= 1) {
        var nb = nbr[o.b], nx = nb[Math.floor(Math.random() * nb.length)];
        if (nx === o.a && nb.length > 1) nx = nb[(nb.indexOf(nx) + 1) % nb.length];
        o.a = o.b; o.b = nx; o.t -= 1;
      }
    }
  }

  function frame(now) {
    raf = 0;
    if (!running) return;
    var dt = lastT ? Math.min(64, now - lastT) : 16; // 탭을 오래 비웠다 돌아와도 한 번에 튀지 않게
    lastT = now;
    if (!still && now - touched > 6000 && now - lastAuto > 3500) { fire(autoPair ? 2 : 1, now); autoPair = !autoPair; lastAuto = now; }
    while (queue.length && queue[0] <= now) { queue.shift(); pulse(entry(shot++), null, null, now); }
    acc += dt;
    while (acc >= STEP) { step(); acc -= STEP; }
    moveIons(dt);
    draw(now, acc / STEP);
    if (still && now - touched > 4000 && !rings.length) { running = false; return; }
    raf = requestAnimationFrame(frame);
  }
  function setRunning() {
    var want = visible && !document.hidden && (!still || performance.now() - touched < 4000);
    if (want === running) return;
    running = want; lastT = 0;
    if (running && !raf) raf = requestAnimationFrame(frame);
  }

  // 움직임 줄이기: 펄스가 번진 한 장면
  function stillFrame() {
    var now = performance.now();
    fire(1, now);
    for (var i = 0; i < 12; i++) step();
    rings = [];
    draw(now, 1);
  }

  build();
  if (still) stillFrame();
  else { lastAuto = performance.now(); fire(1, lastAuto); draw(lastAuto, 0); }

  net.addEventListener("pointerdown", function (ev) {
    var r = net.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top, now = performance.now();
    touched = now;
    pulse(nearest(x, y), x, y, now);
    setRunning();
  });

  // 창 크기뿐 아니라 그림 칸 크기가 바뀌어도(진도 줄이 나중에 붙어 첫 화면이 길어질 때) 다시 그린다
  var rt = 0;
  function refit() {
    clearTimeout(rt);
    rt = setTimeout(function () {
      var r = fig.getBoundingClientRect();
      if (Math.abs(r.width - W) < 2 && Math.abs(r.height - H) < 2) return;
      build();
      if (still) stillFrame(); else draw(performance.now(), 0);
    }, 120);
  }
  if ("ResizeObserver" in window) new ResizeObserver(refit).observe(fig);
  else window.addEventListener("resize", refit);
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (es) { visible = es[0].isIntersecting; setRunning(); }).observe(fig);
  }
  document.addEventListener("visibilitychange", setRunning);
  setRunning();
})();
