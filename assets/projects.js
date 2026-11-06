/* 프로젝트 페이지 전용 (2026-11-06 학습 피드백).
   - 화면 상자(.screen)에 제목 막대('예상 출력' 꼬리표 + 창 이름)를 붙인다.
   - 실습 코드 상자(.labcode)를 접고, 실습 목록·'다음 실습' 단추를 만든다.
   - 화면 속 `C:\...\python>` 줄은 '프롬프트(창이 기다리는 자리)'와 '내가 넣은 명령'으로 나눠 색을 다르게 칠한다.
   - .typed 상자(붙여 넣은 모습)는 내가 넣는 부분을 노란 칸으로 표시하고 아래에 설명 한 줄을 단다.
   각 프로젝트 qmd 첫 줄의 html 블록이 이 파일을 읽는다. */
(function () {
  "use strict";
  var PROMPT = /^((?:PS )?[A-Za-z]:\\[^>]*>)(.*)$/;   // 명령 프롬프트와 VS Code 터미널(PS …>) 둘 다

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function addBar(box) {
    if (box.querySelector(":scope > .screen-bar")) return;
    var bar = el("div", "screen-bar");
    // 2026-11-06 검토: 맥 창 점 장식 대신 '예상 출력'임을 밝히는 꼬리표
    bar.appendChild(el("span", "screen-kind", box.classList.contains("typed") ? "붙여 넣은 모습" : "예상 출력"));
    bar.appendChild(el("span", "screen-title", box.getAttribute("data-screen-title") || "명령 프롬프트"));
    box.insertBefore(bar, box.firstChild);
    box.classList.add("has-bar");
  }

  function decorate(box) {
    var typed = box.classList.contains("typed");
    box.querySelectorAll("pre code").forEach(function (code) {
      var lines = code.textContent.replace(/\n$/, "").split("\n");
      code.textContent = "";
      lines.forEach(function (ln, i) {
        var m = ln.match(PROMPT);
        if (m) {
          code.appendChild(el("span", "sc-prompt", m[1]));
          if (m[2]) {
            code.appendChild(el("span", typed ? "sc-cmd sc-mine" : "sc-cmd", m[2]));
          }
          if (i === lines.length - 1) code.appendChild(el("span", "sc-cursor"));
        } else {
          code.appendChild(document.createTextNode(ln));
        }
        if (i < lines.length - 1) code.appendChild(document.createTextNode("\n"));
      });
    });
    if (typed && !box.querySelector(":scope > .sc-hint")) {
      box.appendChild(el("div", "sc-hint", "노란 칸 = 내가 붙여 넣은 명령. 앞의 C:\\…\\python> 는 창에 원래 있던 글자이니 따라 쓰지 않습니다. 붙여 넣은 뒤 Enter."));
    }
  }

  // .answer 상자 → '정답 보기' 접는 상자 (먼저 스스로 생각하게)
  function answers() {
    document.querySelectorAll("div.answer").forEach(function (d) {
      var det = el("details", "answer");
      det.appendChild(el("summary", null, d.getAttribute("data-label") || "정답 보기 (먼저 스스로 생각해 본 뒤에 누르기)"));
      var body = el("div", "answer-body");
      while (d.firstChild) body.appendChild(d.firstChild);
      det.appendChild(body);
      d.parentNode.replaceChild(det, d);
    });
  }

  // 실습 코드 상자 (2026-11-06 검토: 코드가 페이지에서 가장 큰 덩어리가 되지 않게)
  // 기본: 접힘 + '1. 바꿔 볼 수 있는 설정값' 상자만 미리 보기. 펼치면 전체 코드(안쪽 스크롤 없음),
  // '0. 그림 설정' 같은 공통 설정은 흐리게, 설정값 상자는 노랗게. 복사는 접혀 있어도 항상 실행 가능한 전체 코드.
  function labcode() {
    document.querySelectorAll("div.labcode").forEach(function (box) {
      var src = box.querySelector("div.sourceCode");
      var code = src && src.querySelector("pre code");
      if (!code || box.dataset.ready) return;
      box.dataset.ready = "1";
      var spans = Array.prototype.filter.call(code.children, function (c) {
        return c.tagName === "SPAN";
      });
      var text = spans.map(function (sp) {
        return sp.textContent;
      });
      var n = text.length;
      var heads = [];
      text.forEach(function (t, i) {
        var m = t.match(/^# (\d+)\. /);
        if (m && i > 0 && /^# =+/.test(text[i - 1])) heads.push({ at: i - 1, num: +m[1] });
      });
      function range(num) {
        for (var k = 0; k < heads.length; k++)
          if (heads[k].num === num) return [heads[k].at, k + 1 < heads.length ? heads[k + 1].at : n];
        return null;
      }
      var common = range(0),
        sets = range(1);
      if (sets && !/설정/.test(text[sets[0] + 1] || "")) sets = null;   // 1번 상자가 '설정값'일 때만 미리 보기
      var i;
      if (common) for (i = common[0]; i < common[1]; i++) spans[i].classList.add("lc-common");
      if (sets) for (i = sets[0]; i < sets[1]; i++) spans[i].classList.add("lc-sets");
      var fnEl = box.querySelector(".code-with-filename-file");
      var base = fnEl ? fnEl.textContent.trim().split("/").pop() : "";
      var bar = el("div", "lab-bar");
      var copy = el("button", "lab-btn lab-copy", "전체 코드 복사");
      copy.type = "button";
      copy.addEventListener("click", function () {
        var full = code.textContent.replace(/\n+$/, "") + "\n";
        function done() {
          copy.textContent = "복사됨 ✓ 전체 " + n + "줄";
          setTimeout(function () {
            copy.textContent = "전체 코드 복사";
          }, 1800);
        }
        function fallback() {
          var ta = document.createElement("textarea");
          ta.value = full;
          ta.style.position = "fixed";
          ta.style.opacity = "0";
          document.body.appendChild(ta);
          ta.select();
          try {
            document.execCommand("copy");
            done();
          } catch (e) {}
          document.body.removeChild(ta);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(full).then(done, fallback);
        else fallback();
      });
      var tog = el("button", "lab-btn lab-tog");
      tog.type = "button";
      bar.appendChild(copy);
      bar.appendChild(tog);
      if (/\.py$/.test(base)) {
        var dl = el("a", "lab-btn lab-dl", ".py 파일 받기");
        dl.href = "code/labs/" + base;
        dl.setAttribute("download", base);
        dl.title = "받은 파일을 ion-projects-code\\mylabs 폴더로 옮기면 붙여 넣기와 같습니다";
        bar.appendChild(dl);
      }
      var peek = null;
      if (sets) {
        peek = el("div", "lab-peek");
        peek.appendChild(el("div", "lab-peek-k", "이번에 바꿔 볼 설정값 (코드의 1번 상자 · 펼치면 노란 줄)"));
        var pre = el("pre", "sourceCode");
        var c2 = el("code", "sourceCode python");
        for (i = sets[0] + 3; i < sets[1] && i < n; i++) {
          var cl = spans[i].cloneNode(true);
          cl.removeAttribute("id");
          cl.classList.remove("lc-sets");
          c2.appendChild(cl);
          c2.appendChild(document.createTextNode("\n"));
        }
        while (c2.lastChild && /^\s*$/.test(c2.lastChild.textContent)) c2.removeChild(c2.lastChild);
        pre.appendChild(c2);
        peek.appendChild(pre);
      }
      src.parentNode.insertBefore(bar, src);
      if (peek) src.parentNode.insertBefore(peek, src);
      function set(open) {
        box.classList.toggle("is-open", open);
        tog.textContent = open ? "전체 코드 접기" : "전체 코드 펼치기 · " + n + "줄";
        tog.setAttribute("aria-expanded", open ? "true" : "false");
      }
      tog.addEventListener("click", function () {
        set(!box.classList.contains("is-open"));
      });
      set(false);
    });
  }

  // 긴 페이지에서 '지금 할 실습 하나' (2026-11-06 검토): 맨 위 실습 목록(멈춰도 되는 곳 표시) + 화면 아래 '다음 실습' 단추
  function labNav() {
    var main = document.querySelector("main");
    if (!main) return;
    var heads = Array.prototype.filter.call(main.querySelectorAll("section.level3[id] > h3"), function (h) {   // Quarto는 id를 h3가 아니라 section에 단다
      return /(^|\s)실습\s*\d+\./.test(h.textContent.trim());
    });
    if (heads.length < 3) return;
    function short(h) {
      return h.textContent.trim().replace(/\s*\([^()]*\)\s*$/, "");
    }
    function tag(h) {
      var m = short(h).match(/실습\s*\d+/);
      return m ? m[0] : short(h);
    }
    var groups = [];
    heads.forEach(function (h) {
      var sec = h.closest("section.level2");
      var h2 = sec && sec.querySelector(":scope > h2");
      var key = h2 ? h2.textContent.trim() : "";
      if (!groups.length || groups[groups.length - 1].key !== key) groups.push({ key: key, items: [] });
      groups[groups.length - 1].items.push(h);
    });
    var nav = el("nav", "lab-nav");
    nav.id = "lab-nav";
    nav.setAttribute("aria-label", "실습 바로 가기");
    nav.appendChild(el("div", "lab-nav-k", "실습 바로 가기 · 모두 " + heads.length + "개"));
    groups.forEach(function (g, gi) {
      var box = el("div", "ln-group");
      if (g.key) box.appendChild(el("div", "ln-h", g.key));
      var ol = el("ol");
      g.items.forEach(function (h) {
        var li = el("li");
        var a = el("a", null, short(h));
        a.href = "#" + h.parentNode.id;
        li.appendChild(a);
        ol.appendChild(li);
      });
      box.appendChild(ol);
      nav.appendChild(box);
      if (gi < groups.length - 1) nav.appendChild(el("div", "ln-stop", "여기까지 하고 멈춰도 됩니다"));
    });
    var anchor = document.querySelector(".pj-flow") || document.querySelector(".pj-hero");
    if (!anchor) return;
    anchor.parentNode.insertBefore(nav, anchor.nextSibling);
    var pill = el("a", "lab-pill");
    pill.hidden = true;
    document.body.appendChild(pill);
    var endEl = document.querySelector(".pj-finish");
    var ticking = false;
    function update() {
      ticking = false;
      var cur = -1;
      for (var i = 0; i < heads.length; i++) if (heads[i].getBoundingClientRect().top < Math.max(200, window.innerHeight * 0.3)) cur = i;
      var past = endEl && endEl.getBoundingClientRect().top < window.innerHeight * 0.7;
      if (cur < 0 || past) {
        pill.hidden = true;
        return;
      }
      pill.hidden = false;
      var nx = heads[cur + 1];
      pill.textContent = "지금 " + tag(heads[cur]) + (nx ? " · 다음 " + tag(nx) + " ↓" : " · 마지막 실습 · 목록 ↑");
      pill.href = nx ? "#" + nx.parentNode.id : "#lab-nav";
    }
    window.addEventListener(
      "scroll",
      function () {
        if (!ticking) {
          ticking = true;
          requestAnimationFrame(update);
        }
      },
      { passive: true }
    );
    window.addEventListener("hashchange", function () {
      setTimeout(update, 300);
    });
    update();
  }

  function run() {
    answers();
    labcode();
    labNav();
    document.querySelectorAll(".screen").forEach(function (box) {
      addBar(box);
      decorate(box);
    });
    // 회색 명령 상자의 복사 단추에 글자 붙이기 (아이콘만으로는 단추인지 모름)
    document.querySelectorAll(".code-copy-outer-scaffold .code-copy-button").forEach(function (b) {
      if (b.closest(".screen")) return;
      b.setAttribute("title", "복사");
      b.setAttribute("aria-label", "명령 복사");
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
  else run();
})();
