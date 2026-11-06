/* 프로젝트 페이지 전용 (2026-11-06 학습 피드백).
   - '명령 프롬프트' 화면 상자(.screen)에 제목 막대(빨강·노랑·초록 점 + 창 이름)를 붙인다.
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
    var dots = el("span", "screen-dots");
    dots.setAttribute("aria-hidden", "true");
    dots.appendChild(el("i"));
    dots.appendChild(el("i"));
    dots.appendChild(el("i"));
    bar.appendChild(dots);
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

  function run() {
    answers();
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
