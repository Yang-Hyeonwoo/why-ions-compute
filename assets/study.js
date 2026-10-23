/* 공부 사이트 동작
 * - 내 컴퓨터에서 tools/server.py로 열면(로컬 모드) 사이트 안에서 글을 쓰고 저장한다.
 * - 웹에 공개된 사이트(정적 모드)에서는 저장된 글을 읽기만 한다. 기본으로 읽기 모드로 연다.
 *
 * 상태는 두 가지로 나뉜다.
 *   FILES: 어떤 글이 저장되어 있는가 (answers/*.md, 초안 저장)
 *   DAYS:  내가 직접 누른 단계 체크와 '오늘 학습 완료' (answers/status.json)
 * 답이 저장되어 있다는 이유만으로 완료로 치지 않는다.
 */
(function () {
  "use strict";

  var OFFSET = window.STUDY_OFFSET || "./";
  var CFG = window.STUDY_CONFIG || {};
  var CDN = {
    marked: "https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js",
    katex: "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js",
    autorender: "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js",
  };
  var TAGS = [
    ["[확인]", "tag-fact", "확인"],
    ["[해석]", "tag-interp", "해석"],
    ["[가설]", "tag-hypo", "가설"],
    ["[미확인]", "tag-unverified", "미확인"],
  ];

  var LOCAL = false;
  var FILES = {}; // 파일 이름 -> 마지막 저장 시각
  var DAYS = {}; // d01 -> {lesson, note, done}
  var EDITORS = {};
  var templates = {};

  // ---------- 작은 도구들 ----------
  function h(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text != null) el.textContent = text;
    return el;
  }
  function button(label, cls, onClick) {
    var b = h("button", "sbtn " + (cls || ""), label);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }
  function pad(n) {
    return n < 10 ? "0" + n : "" + n;
  }
  function fmtTime(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return "";
    return d.getMonth() + 1 + "/" + d.getDate() + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function todayIso() {
    var d = new Date();
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }
  function escapeHtml(s) {
    return s.replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function store(key, value) {
    try {
      if (value == null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (e) {}
  }
  function recall(key) {
    try {
      return localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }
  function toast(msg, long) {
    var t = document.getElementById("study-toast");
    if (!t) {
      t = h("div");
      t.id = "study-toast";
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(t._timer);
    t._timer = setTimeout(function () {
      t.classList.remove("show");
    }, long ? 6000 : 2200);
  }
  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }
  var depsPromise = null;
  function deps() {
    if (!depsPromise) {
      depsPromise = loadScript(CDN.marked)
        .then(function () {
          return loadScript(CDN.katex);
        })
        .then(function () {
          return loadScript(CDN.autorender);
        })
        .catch(function () {});
    }
    return depsPromise;
  }

  // ---------- 마크다운 → 화면 ----------
  function renderMarkdown(md) {
    if (!window.marked) return "<pre>" + escapeHtml(md) + "</pre>";
    var math = [];
    var src = md
      .replace(/\$\$([\s\S]+?)\$\$/g, function (m) {
        math.push(m);
        return "@@MATH" + (math.length - 1) + "@@";
      })
      .replace(/(^|[^\\$])\$([^\s$](?:[^$\n]*?[^\s$])?)\$/g, function (m, pre, body) {
        math.push("$" + body + "$");
        return pre + "@@MATH" + (math.length - 1) + "@@";
      });
    var html = window.marked.parse(src, { gfm: true, breaks: true });
    html = html.replace(/@@MATH(\d+)@@/g, function (m, i) {
      return escapeHtml(math[+i]);
    });
    TAGS.forEach(function (t) {
      html = html.split(t[0]).join('<span class="tag ' + t[1] + '">' + t[2] + "</span>");
    });
    return html;
  }
  function typeset(el) {
    if (!window.renderMathInElement) return;
    window.renderMathInElement(el, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
    });
  }

  // ---------- 저장소 ----------
  function api(path, opts) {
    return fetch("/api/" + path, Object.assign({ cache: "no-store" }, opts || {})).then(
      function (r) {
        return r.json().then(function (j) {
          if (!r.ok) throw new Error(j.error || r.status);
          return j;
        });
      },
      function () {
        throw new Error("서버에 연결할 수 없어요. '사이트 열기' 창이 닫혔는지 확인하세요.");
      }
    );
  }
  function detectMode() {
    return fetch("/api/ping", { cache: "no-store" })
      .then(function (r) {
        return r.ok ? r.json() : {};
      })
      .then(function (j) {
        LOCAL = !!j.ok;
      })
      .catch(function () {
        LOCAL = false;
      })
      .then(function () {
        document.body.classList.add(LOCAL ? "local-mode" : "static-mode");
      });
  }
  function fetchJson(url) {
    return fetch(url, { cache: "no-store" })
      .then(function (r) {
        return r.ok ? r.json() : {};
      })
      .catch(function () {
        return {};
      });
  }
  function loadStatus() {
    if (LOCAL) {
      return api("status")
        .then(function (s) {
          FILES = s.files || {};
          DAYS = s.days || {};
        })
        .catch(function () {
          FILES = {};
          DAYS = {};
        });
    }
    return Promise.all([fetchJson(OFFSET + "answers/index.json"), fetchJson(OFFSET + "answers/status.json")]).then(
      function (r) {
        FILES = r[0] || {};
        DAYS = r[1] || {};
      }
    );
  }
  function loadContent(name) {
    if (LOCAL) return api("answers/" + name);
    return fetch(OFFSET + "answers/" + name + ".md", { cache: "no-store" })
      .then(function (r) {
        return r.ok ? r.text() : "";
      })
      .then(function (text) {
        return { content: text, updated: null };
      })
      .catch(function () {
        return { content: "", updated: null };
      });
  }
  function loadTemplate(name) {
    if (!name) return Promise.resolve("");
    if (templates[name] != null) return Promise.resolve(templates[name]);
    return fetch(OFFSET + "templates/" + name + ".md", { cache: "no-store" })
      .then(function (r) {
        return r.ok ? r.text() : "";
      })
      .catch(function () {
        return "";
      })
      .then(function (t) {
        templates[name] = t;
        return t;
      });
  }

  // ---------- 사이트 안에서 쓰는 칸 ----------
  function Editable(el) {
    this.el = el;
    this.name = el.dataset.file;
    this.title = el.dataset.title || "";
    this.template = el.dataset.template;
    this.lock = el.dataset.lock === "true";
    this.placeholder = el.dataset.placeholder || "";
    this.content = "";
    this.updated = null;
    this.dirty = false;
    EDITORS[this.name] = this;
  }
  Editable.prototype.isEmpty = function () {
    return !this.content.trim();
  };
  Editable.prototype.init = function () {
    var self = this;
    return loadContent(this.name).then(function (data) {
      self.content = (data && data.content) || "";
      self.updated = (data && data.updated) || null;
      self.renderView();
      // 저장하지 않은 임시 글이 있으면 알려 준다
      var draft = recall("study-draft:" + self.name);
      if (LOCAL && draft && draft.trim() && draft !== self.content) {
        self.showDraftNotice();
      }
    });
  };
  Editable.prototype.showDraftNotice = function () {
    var self = this;
    var bar = h("div", "draft-notice");
    bar.appendChild(h("span", "", "저장하지 않은 임시 글이 있어요."));
    bar.appendChild(
      button("불러오기", "primary", function () {
        self.buildEditor(recall("study-draft:" + self.name) || "");
      })
    );
    bar.appendChild(
      button("버리기", "ghost", function () {
        store("study-draft:" + self.name, null);
        bar.remove();
      })
    );
    this.el.appendChild(bar);
  };
  Editable.prototype.renderView = function () {
    var self = this;
    this.dirty = false;
    this.el.innerHTML = "";
    var head = h("div", "ed-head");
    var title = h("div", "ed-title", this.title);
    if (this.updated) title.appendChild(h("span", "ed-meta", "초안 저장 " + fmtTime(this.updated)));
    head.appendChild(title);
    var btns = h("div", "btn-row local-only");
    btns.appendChild(
      button(this.isEmpty() ? "쓰기" : "수정", this.isEmpty() ? "primary" : "", function () {
        self.startEdit();
      })
    );
    if (!this.isEmpty())
      btns.appendChild(
        button("이력", "ghost", function () {
          openHistory(self.name, self.title);
        })
      );
    head.appendChild(btns);
    this.el.appendChild(head);

    var view = h("div", "ed-view");
    if (this.isEmpty()) {
      view.classList.add("empty");
      view.textContent = LOCAL ? "아직 쓰지 않았어요. 오른쪽 위 [쓰기]를 누르세요." : "아직 작성되지 않았습니다.";
    } else {
      view.innerHTML = renderMarkdown(this.content);
      typeset(view);
    }
    this.el.appendChild(view);
    document.dispatchEvent(new CustomEvent("study:changed"));
  };
  Editable.prototype.startEdit = function () {
    var self = this;
    if (this.lock && !this.isEmpty()) {
      if (!confirm("읽기 전 답은 원칙상 고치지 않습니다. 오타만 고칠 건가요?")) return;
    }
    var base = this.isEmpty() ? loadTemplate(this.template) : Promise.resolve(this.content);
    base.then(function (text) {
      var draft = recall("study-draft:" + self.name);
      if (draft && draft !== text && draft !== self.content) {
        if (confirm("저장하지 않은 임시 글이 있습니다. 불러올까요?")) text = draft;
      }
      self.buildEditor(text);
    });
  };
  Editable.prototype.buildEditor = function (text) {
    var self = this;
    this.el.innerHTML = "";

    var head = h("div", "ed-head");
    head.appendChild(h("div", "ed-title", this.title + " · 쓰는 중"));
    this.el.appendChild(head);

    var bar = h("div", "ed-toolbar");
    var ta = h("textarea");
    var preview = h("div", "ed-preview");
    var panes = h("div", "ed-panes");
    if (window.innerWidth < 900) panes.classList.add("single");

    function insert(before, after, sample) {
      var s = ta.selectionStart,
        e = ta.selectionEnd;
      var sel = ta.value.slice(s, e) || sample || "";
      ta.setRangeText(before + sel + (after || ""), s, e, "end");
      if (!ta.value.slice(s, e) && sample) {
        ta.selectionStart = s + before.length;
        ta.selectionEnd = s + before.length + sample.length;
      }
      ta.focus();
      onInput();
    }
    TAGS.slice(0, 3).forEach(function (t) {
      bar.appendChild(
        button(t[2], "tagbtn", function () {
          insert(t[0] + " ", "");
        })
      );
    });
    bar.appendChild(h("span", "sep"));
    bar.appendChild(
      button("굵게", "tagbtn", function () {
        insert("**", "**", "강조");
      })
    );
    bar.appendChild(
      button("수식", "tagbtn", function () {
        insert("$", "$", "\\tau \\sim L^2/D");
      })
    );
    bar.appendChild(
      button("표", "tagbtn", function () {
        insert("\n| 항목 | 내용 |\n|---|---|\n| ", " |  |\n", "");
      })
    );
    bar.appendChild(
      button("목록", "tagbtn", function () {
        insert("\n- ", "", "");
      })
    );
    bar.appendChild(h("span", "sep"));
    bar.appendChild(
      button("미리보기", "tagbtn", function () {
        panes.classList.toggle("single");
      })
    );
    this.el.appendChild(bar);

    ta.value = text;
    ta.placeholder = this.placeholder;
    panes.appendChild(ta);
    panes.appendChild(preview);
    this.el.appendChild(panes);

    var foot = h("div", "ed-foot");
    foot.appendChild(h("span", "", "Ctrl+S 초안 저장 · 마크다운과 $수식$을 쓸 수 있어요 · 쓰는 동안 임시 글이 브라우저에 남아요"));
    var actions = h("div", "btn-row");
    actions.appendChild(
      button("취소", "", function () {
        if (self.dirty && !confirm("저장하지 않은 내용을 버릴까요?")) return;
        store("study-draft:" + self.name, null);
        self.renderView();
      })
    );
    var saveBtn = button("초안 저장", "primary", function () {
      self.save(ta.value, saveBtn);
    });
    actions.appendChild(saveBtn);
    foot.appendChild(actions);
    this.el.appendChild(foot);

    var timer = null;
    function refresh() {
      preview.innerHTML = renderMarkdown(ta.value);
      typeset(preview);
    }
    function onInput() {
      self.dirty = ta.value !== self.content;
      clearTimeout(timer);
      timer = setTimeout(function () {
        refresh();
        store("study-draft:" + self.name, ta.value);
      }, 250);
    }
    function grow() {
      ta.style.height = "auto";
      ta.style.height = Math.max(320, ta.scrollHeight + 4) + "px";
    }
    ta.addEventListener("input", function () {
      onInput();
      grow();
    });
    ta.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
        e.preventDefault();
        self.save(ta.value, saveBtn);
      }
    });
    refresh();
    grow();
    ta.focus();
    this.el.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  Editable.prototype.save = function (text, btn) {
    var self = this;
    var content = text.replace(/\r\n/g, "\n");
    if (btn) btn.disabled = true;
    api("answers/" + this.name, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: content }),
    })
      .then(function (j) {
        self.content = content;
        self.updated = j.updated;
        if (content.trim()) FILES[self.name] = j.updated;
        else delete FILES[self.name];
        store("study-draft:" + self.name, null);
        self.renderView();
        toast(j.committed ? "초안을 저장했어요 · 수정 이력에 남겼어요" : "초안을 저장했어요");
      })
      .catch(function (err) {
        if (btn) btn.disabled = false;
        toast("저장하지 못했어요: " + err.message + " 쓴 글은 임시 글로 남아 있어요.", true);
      });
  };

  window.addEventListener("beforeunload", function (e) {
    for (var k in EDITORS) {
      if (EDITORS[k].dirty) {
        e.preventDefault();
        e.returnValue = "";
        return;
      }
    }
  });

  // ---------- 수정 이력 ----------
  function openHistory(name, title) {
    api("history/" + name)
      .then(function (list) {
        var back = h("div", "hist-backdrop");
        var modal = h("div", "hist-modal");
        var side = h("div", "hist-list");
        var body = h("div", "hist-body");
        side.appendChild(h("div", "hl-title", title + " · 이력 " + list.length + "개"));
        function close() {
          back.remove();
          document.removeEventListener("keydown", onKey);
        }
        function onKey(e) {
          if (e.key === "Escape") close();
        }
        var closeBtn = button("닫기", "hist-close", close);
        list.forEach(function (item, i) {
          var b = h("button", "", fmtTime(item.date) + (i === 0 ? " · 최신" : ""));
          b.addEventListener("click", function () {
            side.querySelectorAll("button").forEach(function (x) {
              x.classList.remove("active");
            });
            b.classList.add("active");
            api("history/" + name + "/" + item.hash).then(function (j) {
              body.innerHTML = renderMarkdown(j.content || "");
              body.appendChild(closeBtn);
              typeset(body);
            });
          });
          side.appendChild(b);
          if (i === 0)
            setTimeout(function () {
              b.click();
            }, 0);
        });
        if (!list.length) body.appendChild(h("p", "", "아직 이력이 없습니다."));
        body.appendChild(closeBtn);
        modal.appendChild(side);
        modal.appendChild(body);
        back.appendChild(modal);
        back.addEventListener("click", function (e) {
          if (e.target === back) close();
        });
        document.addEventListener("keydown", onKey);
        document.body.appendChild(back);
      })
      .catch(function (err) {
        toast("이력을 불러오지 못했어요: " + err.message, true);
      });
  }

  // ---------- 날짜 상태 ----------
  // done: 내가 '오늘 학습 완료'를 누름 / started: 무엇이든 저장했거나 체크함 / "": 아직
  function dayState(did) {
    var d = DAYS[did] || {};
    if (d.done) return "done";
    if (FILES[did + "-pre"] || FILES[did + "-answer"] || d.lesson || d.note) return "started";
    return "";
  }
  function setDayStatus(did, patch) {
    return api("status/" + did, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }).then(function (j) {
      if (j.status && Object.keys(j.status).length) DAYS[did] = j.status;
      else delete DAYS[did];
      applyStatus();
      return j;
    });
  }
  function applyStatus() {
    document.querySelectorAll(".pb-day[data-day]").forEach(function (el) {
      var st = dayState(el.dataset.day);
      el.classList.toggle("st-done", st === "done");
      el.classList.toggle("st-started", st === "started");
      el.classList.toggle("is-today", el.dataset.date === todayIso());
    });
    document.querySelectorAll(".day-status[data-day]").forEach(function (el) {
      var st = dayState(el.dataset.day);
      el.textContent = st === "done" ? "완료" : st === "started" ? "진행 중" : "예정";
      el.className = "day-status" + (st ? " st-" + st : "");
    });
    document.querySelectorAll("#quarto-sidebar a.sidebar-link").forEach(function (a) {
      var m = (a.getAttribute("href") || "").match(/days\/(d\d\d)\.html/);
      if (!m) return;
      var old = a.querySelector(".sb-dot");
      if (old) old.remove();
      var st = dayState(m[1]);
      if (!st) return;
      var text = a.querySelector(".sidebar-item-text") || a;
      text.appendChild(h("span", "sb-dot st-" + st));
    });
    document.querySelectorAll(".day-steps[data-day]").forEach(function (ol) {
      var did = ol.dataset.day;
      var d = DAYS[did] || {};
      var map = {
        pre: !!FILES[did + "-pre"],
        lesson: !!d.lesson,
        note: !!d.note,
        answer: !!FILES[did + "-answer"],
        done: !!d.done,
      };
      ol.querySelectorAll("li").forEach(function (li) {
        li.classList.toggle("done", !!map[li.dataset.step]);
      });
    });
    document.querySelectorAll("input[data-step-check]").forEach(function (cb) {
      var d = DAYS[cb.dataset.day] || {};
      cb.checked = !!d[cb.dataset.stepCheck];
    });
    document.querySelectorAll(".done-box[data-day]").forEach(function (box) {
      var d = DAYS[box.dataset.day] || {};
      box.classList.toggle("is-done", !!d.done);
      var desc = box.querySelector(".done-desc");
      if (d.done && desc) desc.textContent = "완료한 날: " + fmtTime(d.done) + ". 답은 계속 고칠 수 있어요.";
      var st = box.querySelector(".done-static");
      if (st) st.textContent = d.done ? "학습 완료 " + fmtTime(d.done) : "";
    });
  }
  function setupStepChecks() {
    document.querySelectorAll("input[data-step-check]").forEach(function (cb) {
      cb.addEventListener("change", function () {
        var patch = {};
        patch[cb.dataset.stepCheck] = cb.checked;
        setDayStatus(cb.dataset.day, patch).catch(function (err) {
          cb.checked = !cb.checked;
          toast("저장하지 못했어요: " + err.message, true);
        });
      });
    });
    document.querySelectorAll(".done-box[data-day]").forEach(function (box) {
      var did = box.dataset.day;
      var doneBtn = box.querySelector('[data-action="done"]');
      var undoneBtn = box.querySelector('[data-action="undone"]');
      doneBtn.addEventListener("click", function () {
        var d = DAYS[did] || {};
        var missing = [];
        if (!FILES[did + "-answer"]) missing.push("내 답 저장");
        if (!d.lesson) missing.push("학습자료 읽음 체크");
        if (!d.note) missing.push("노트 정리 체크");
        if (missing.length && !confirm("아직 안 한 것: " + missing.join(", ") + ". 그래도 완료로 표시할까요?")) return;
        setDayStatus(did, { done: true })
          .then(function () {
            toast("D" + parseInt(did.slice(1), 10) + " 학습 완료로 표시했어요");
          })
          .catch(function (err) {
            toast("저장하지 못했어요: " + err.message, true);
          });
      });
      undoneBtn.addEventListener("click", function () {
        setDayStatus(did, { done: false }).catch(function (err) {
          toast("저장하지 못했어요: " + err.message, true);
        });
      });
    });
  }

  // ---------- 학습자료 가리개 ----------
  function setupGates() {
    if (!LOCAL) return;
    document.querySelectorAll(".lesson-body[data-pre]").forEach(function (lb) {
      var pre = lb.dataset.pre;
      if (FILES[pre] || recall("study-gate-open:" + pre)) return;
      if (lb.querySelector(".gate")) return;
      lb.classList.add("gated");
      var gate = h("div", "gate");
      var p = h("p");
      p.innerHTML =
        "<b>읽기 전 답을 먼저 써 볼까요?</b><br>자료를 보기 전에 10분 동안 지금 아는 만큼 써 두면, 공부가 끝난 뒤 무엇을 배웠는지 분명해집니다.";
      gate.appendChild(p);
      var row = h("div", "btn-row");
      row.appendChild(
        button("읽기 전 답 쓰기", "primary", function () {
          var ed = EDITORS[pre];
          if (ed) ed.startEdit();
        })
      );
      row.appendChild(
        button("그냥 읽기", "", function () {
          store("study-gate-open:" + pre, "1");
          ungate(lb);
        })
      );
      gate.appendChild(row);
      lb.insertBefore(gate, lb.firstChild);
    });
  }
  function ungate(lb) {
    lb.classList.remove("gated");
    var g = lb.querySelector(".gate");
    if (g) g.remove();
  }
  document.addEventListener("study:changed", function () {
    applyStatus();
    document.querySelectorAll(".lesson-body.gated").forEach(function (lb) {
      if (FILES[lb.dataset.pre]) ungate(lb);
    });
  });

  // ---------- 읽기 모드 (후배에게 보여줄 때: 학습자료와 최종 답만 펼친다) ----------
  function setupReadMode() {
    var steps = document.querySelector(".day-steps[data-day]");
    if (!steps) return;
    var FOLD = [
      ["pre", "읽기 전 답"],
      ["note", "노트에 정리"],
      ["done", "학습 완료"],
      ["feedback", "피드백과 꼬리질문"],
      ["questions", "Claude에게 질문"],
    ];
    var on = LOCAL ? recall("study-read-mode") === "1" : true;
    function apply() {
      document.body.classList.toggle("read-mode", on);
      FOLD.forEach(function (f) {
        var sec = document.getElementById(f[0]);
        if (!sec) return;
        var wrap = sec.querySelector(":scope > details.fold");
        if (on && !wrap) {
          var d = h("details", "fold");
          var s = h("summary", "", f[1] + " 펼치기");
          d.appendChild(s);
          var kids = Array.prototype.slice.call(sec.children).filter(function (k) {
            return !/^H[1-6]$/.test(k.tagName);
          });
          kids.forEach(function (k) {
            d.appendChild(k);
          });
          sec.appendChild(d);
        } else if (!on && wrap) {
          Array.prototype.slice.call(wrap.children).forEach(function (k) {
            if (k.tagName !== "SUMMARY") sec.appendChild(k);
          });
          wrap.remove();
        }
      });
      var btn = document.querySelector('[data-action="read-mode"]');
      if (btn) btn.textContent = on ? "공부 모드로" : "읽기 모드";
    }
    var btn = document.querySelector('[data-action="read-mode"]');
    if (btn)
      btn.addEventListener("click", function () {
        on = !on;
        store("study-read-mode", on ? "1" : null);
        apply();
      });
    apply();
  }

  // ---------- 커버 페이지: 오늘의 질문 / 이어서 할 질문 ----------
  function setupToday() {
    var card = document.getElementById("today-card");
    var dataEl = document.getElementById("study-days");
    if (!card || !dataEl) return;
    var days = JSON.parse(dataEl.textContent);
    var today = todayIso();
    var todays = days.find(function (d) {
      return d.date === today;
    });
    var firstOpen = days.find(function (d) {
      return dayState(d.day) !== "done";
    });
    var late = days.filter(function (d) {
      return d.date < today && dayState(d.day) !== "done";
    });
    var done = days.filter(function (d) {
      return dayState(d.day) === "done";
    }).length;

    function dayLine(label, d, primary) {
      var row = h("div", "tc-row");
      var dd = new Date(d.date + "T00:00:00");
      row.appendChild(h("div", "tc-label", label + " · D" + d.n + " · " + (dd.getMonth() + 1) + "월 " + dd.getDate() + "일"));
      row.appendChild(h("div", "tc-title", d.title));
      var a = h("a", "sbtn " + (primary ? "primary" : ""), primary ? "공부 시작 →" : "열기 →");
      a.href = OFFSET + "days/" + d.day + ".html";
      row.appendChild(a);
      return row;
    }

    card.innerHTML = "";
    if (!firstOpen) {
      card.appendChild(h("div", "tc-label", "30일을 모두 완료했습니다"));
      card.appendChild(h("div", "tc-title", "D30의 결정을 다시 읽어 보세요."));
      return;
    }
    if (today < days[0].date) {
      card.appendChild(dayLine("곧 시작", days[0], true));
    } else if (todays && todays.day === firstOpen.day) {
      card.appendChild(dayLine("오늘의 질문", todays, true));
    } else if (firstOpen.date > today) {
      // 오늘 몫은 끝났다
      card.appendChild(dayLine("다음 질문", firstOpen, true));
    } else {
      // 날짜가 밀렸다: 기본 버튼은 가장 먼저 끝내지 못한 날로, 오늘 질문은 따로
      card.appendChild(dayLine("이어서 할 질문 (가장 먼저 끝내지 못한 날)", firstOpen, true));
      if (todays && dayState(todays.day) !== "done") card.appendChild(dayLine("오늘 날짜의 질문", todays, false));
    }
    var meta = h("div", "tc-meta");
    var parts = ["완료 " + done + " / " + days.length + "일"];
    if (late.length)
      parts.push(
        "밀린 날: " +
          late
            .map(function (d) {
              return "D" + d.n;
            })
            .join(", ")
      );
    meta.textContent = parts.join(" · ");
    card.appendChild(meta);
  }

  // ---------- 댓글 ----------
  function setupComments() {
    var sec = document.querySelector("section.comments");
    if (!sec) return;
    var g = CFG.giscus;
    if (g && g.repo) {
      sec.appendChild(h("h3", "cm-title", "댓글"));
      var s = document.createElement("script");
      s.src = "https://giscus.app/client.js";
      s.async = true;
      s.crossOrigin = "anonymous";
      var attrs = {
        "data-repo": g.repo,
        "data-repo-id": g.repoId,
        "data-category": g.category,
        "data-category-id": g.categoryId,
        "data-mapping": "pathname",
        "data-strict": "0",
        "data-reactions-enabled": "1",
        "data-emit-metadata": "0",
        "data-input-position": "top",
        "data-theme": "light",
        "data-lang": "ko",
      };
      Object.keys(attrs).forEach(function (k) {
        s.setAttribute(k, attrs[k]);
      });
      sec.appendChild(s);
    } else if (LOCAL) {
      sec.appendChild(h("h3", "cm-title", "댓글"));
      sec.appendChild(h("div", "cm-off", "댓글창은 사이트를 웹에 공개한 뒤 켜집니다. 후배들이 이 자리에 질문과 의견을 남길 수 있어요."));
    } else {
      sec.remove();
    }
  }

  // ---------- 생활코딩식 머리 영역: 흰 제목 띠를 어두운 메뉴 위에 둔다 ----------
  function setupBrand() {
    var header = document.getElementById("quarto-header");
    if (!header) return;
    var strip = h("div", "site-brand");
    var inner = h("div", "site-brand-inner");
    var a = h("a", "site-brand-title", "Why Ions Compute");
    a.href = OFFSET + "index.html";
    inner.appendChild(a);
    inner.appendChild(h("div", "site-brand-sub", "이온 소자는 어떻게, 왜 계산하는가 · 30일 탐구 노트"));
    strip.appendChild(inner);
    header.insertBefore(strip, header.firstChild);
  }

  // ---------- 읽기 편의 ----------
  function setupFontSize() {
    // Bootstrap의 .fs-1~6 유틸리티 클래스와 겹치지 않게 study- 접두어를 붙인다
    var levels = ["study-fs-1", "study-fs-2", "study-fs-3", "study-fs-4"];
    var cur = parseInt(recall("study-fs") || "2", 10);
    function apply() {
      levels.forEach(function (c) {
        document.documentElement.classList.remove(c);
      });
      document.documentElement.classList.add("study-fs-" + cur);
    }
    apply();
    var tools = document.querySelector(".quarto-navbar-tools") || document.querySelector("#quarto-search");
    if (!tools) return;
    var box = h("span", "fs-control");
    box.title = "글자 크기";
    box.appendChild(
      button("가−", "", function () {
        cur = Math.max(1, cur - 1);
        store("study-fs", cur);
        apply();
      })
    );
    box.appendChild(
      button("가+", "", function () {
        cur = Math.min(4, cur + 1);
        store("study-fs", cur);
        apply();
      })
    );
    tools.appendChild(box);
  }
  function setupProgressBar() {
    var bar = h("div");
    bar.id = "reading-progress";
    document.body.appendChild(bar);
    function update() {
      var max = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.width = (max > 0 ? (window.scrollY / max) * 100 : 0) + "%";
    }
    window.addEventListener("scroll", update, { passive: true });
    update();
  }

  // ---------- 장 내비게이터: 오늘의 지도 + 지금 읽는 장 표시 ----------
  function setupChapters() {
    var lb = document.querySelector(".lesson-body");
    if (!lb) return;
    var heads = Array.prototype.slice.call(lb.querySelectorAll("h3"));
    if (heads.length < 3) return;
    heads.forEach(function (h3, i) {
      if (!h3.id) h3.id = "ch-" + i;
    });
    // 지도
    var map = h("div", "chap-map");
    map.appendChild(h("div", "cm-title", "오늘의 지도 · 읽은 장에는 ✓가 붙습니다"));
    var ol = h("ol");
    heads.forEach(function (h3) {
      var li = h("li");
      var a = h("a", "", h3.textContent.replace(/\s+/g, " ").trim());
      a.href = "#" + h3.id;
      li.appendChild(a);
      li.dataset.target = h3.id;
      ol.appendChild(li);
    });
    map.appendChild(ol);
    var meta = lb.querySelector(".lesson-meta");
    if (meta && meta.nextSibling) lb.insertBefore(map, meta.nextSibling);
    else lb.insertBefore(map, lb.firstChild);
    // 위쪽 고정 표시
    var now = h("div");
    now.id = "chap-now";
    var cn = h("div", "cn");
    now.appendChild(cn);
    document.body.appendChild(now);
    var did = (document.querySelector(".day-steps[data-day]") || {}).dataset;
    var seenKey = "study-seen:" + (did ? did.day : location.pathname);
    var seen = {};
    try {
      seen = JSON.parse(recall(seenKey) || "{}");
    } catch (e) {}
    function update() {
      var y = window.scrollY + 120;
      var cur = -1;
      heads.forEach(function (h3, i) {
        if (h3.getBoundingClientRect().top + window.scrollY <= y) cur = i;
      });
      var rect = lb.getBoundingClientRect();
      var inside = rect.top < 100 && rect.bottom > 200;
      now.classList.toggle("show", inside && cur >= 0);
      if (cur >= 0) {
        cn.innerHTML = "";
        cn.appendChild(h("span", "", "지금 읽는 곳: "));
        cn.appendChild(h("b", "", heads[cur].textContent.replace(/\s+/g, " ").trim()));
        cn.appendChild(h("span", "cn-pos", cur + 1 + " / " + heads.length + "장"));
        // 앞 장들은 읽은 것으로 표시
        for (var i = 0; i < cur; i++) seen[heads[i].id] = 1;
        store(seenKey, JSON.stringify(seen));
      }
      ol.querySelectorAll("li").forEach(function (li, i) {
        li.classList.toggle("cur", i === cur);
        li.classList.toggle("seen", !!seen[li.dataset.target] && i !== cur);
      });
    }
    window.addEventListener("scroll", update, { passive: true });
    update();
  }

  // ---------- 퀴즈 ----------
  function norm(s) {
    return String(s)
      .toLowerCase()
      .replace(/[\s·,.;:()\[\]'"]/g, "")
      .replace(/×/g, "x")
      .replace(/[−–—]/g, "-");
  }
  function setupQuiz() {
    document.querySelectorAll(".quiz[data-day]").forEach(renderQuiz);
  }
  var KIND_LABEL = { check: "잠깐 점검", end: "마무리 퀴즈", final: "종합 퀴즈" };
  var LETTERS = ["A", "B", "C", "D", "E", "F"];
  function renderQuiz(box) {
    var dataEl = document.getElementById("quiz-" + box.dataset.day);
    if (!dataEl) {
      box.remove();
      return;
    }
    var data;
    try {
      data = JSON.parse(dataEl.textContent);
    } catch (e) {
      box.remove();
      return;
    }
    var setId = box.dataset.set;
    var set = (data.sets || {})[setId];
    if (!set || !set.items || !set.items.length) {
      box.remove();
      return;
    }
    var items = set.items;
    var kind = set.kind || "end";
    box.className = "quiz quiz-" + kind;
    var key = "study-quiz:" + box.dataset.day + ":" + setId;
    var saved = {};
    try {
      saved = JSON.parse(recall(key) || "{}");
    } catch (e) {}

    // 머리: 제목 + 진행 점
    var head = h("div", "quiz-head");
    var left = h("div", "quiz-left");
    left.appendChild(h("span", "quiz-kind", KIND_LABEL[kind] || "퀴즈"));
    left.appendChild(h("span", "quiz-title", set.title || ""));
    head.appendChild(left);
    var dots = h("div", "quiz-dots");
    items.forEach(function () {
      dots.appendChild(h("span", "qdot"));
    });
    head.appendChild(dots);
    box.appendChild(head);

    var body = h("div", "quiz-body");
    box.appendChild(body);
    var banner = h("div", "quiz-banner");
    banner.style.display = "none";
    box.appendChild(banner);

    function updateScore() {
      var n = 0,
        ok = 0;
      items.forEach(function (it, i) {
        var d = dots.children[i];
        d.className = "qdot";
        if (saved[i]) {
          n++;
          if (saved[i].ok) ok++;
          d.classList.add(saved[i].ok ? "ok" : "no");
        }
      });
      store(key, JSON.stringify(saved));
      if (n === items.length) {
        banner.style.display = "";
        var msg;
        if (ok === n) msg = n === 1 ? "정확해요. 다음으로 넘어가세요." : "모두 맞혔어요. 이 장은 내 것이 됐습니다.";
        else if (ok >= n * 0.6) msg = "거의 다 왔어요. 틀린 문제의 이유를 한 번만 더 읽어 보세요.";
        else msg = "괜찮아요. 틀린 문제가 오늘 배울 지점입니다. 요점으로 돌아가 보세요.";
        banner.innerHTML =
          "<div class='qb-score'><b>" + ok + "</b> / " + n + "</div><div class='qb-msg'>" + msg + "</div>";
        banner.className = "quiz-banner " + (ok === n ? "all" : ok >= n * 0.6 ? "most" : "few");
      } else {
        banner.style.display = "none";
      }
    }

    items.forEach(function (it, i) {
      var qi = h("div", "qitem");
      var qt = h("div", "qtext");
      qt.appendChild(h("span", "qn", "Q" + (i + 1)));
      var qs = h("span", "qq");
      qs.appendChild(document.createTextNode(it.q));
      qt.appendChild(qs);
      qi.appendChild(qt);
      var why = h("div", "qwhy");
      why.style.display = "none";
      function reveal(ok, chosenText, animate) {
        qi.classList.add("answered", ok ? "is-ok" : "is-no");
        if (animate) {
          qi.classList.add(ok ? "pop" : "shake");
          setTimeout(function () {
            qi.classList.remove("pop", "shake");
          }, 600);
        }
        why.style.display = "";
        why.className = "qwhy " + (ok ? "ok" : "no");
        var ans = it.type === "ox" ? (it.a ? "O (참)" : "X (거짓)") : it.type === "mc" ? it.options[it.a] : it.a[0];
        why.innerHTML =
          "<span class='qw-badge'>" +
          (ok ? "정답" : "오답") +
          "</span> " +
          (ok ? "" : "<b>정답: " + escapeHtml(String(ans)) + "</b> ") +
          escapeHtml(it.why || "");
        saved[i] = { ok: ok, chosen: chosenText };
        updateScore();
      }
      if (it.type === "ox" || it.type === "mc") {
        var opts = it.type === "ox" ? ["O  참", "X  거짓"] : it.options;
        var correct = it.type === "ox" ? (it.a ? 0 : 1) : it.a;
        var row = h("div", "qopts" + (it.type === "ox" ? " ox" : ""));
        opts.forEach(function (o, k) {
          var b = button("", "qopt", function () {
            if (qi.classList.contains("answered")) return;
            row.querySelectorAll(".qopt").forEach(function (x, j) {
              if (j === correct) x.classList.add("right");
              else if (j === k) x.classList.add("wrong");
            });
            reveal(k === correct, o, true);
          });
          if (it.type === "mc") b.appendChild(h("span", "qletter", LETTERS[k]));
          b.appendChild(h("span", "qlabel", o));
          row.appendChild(b);
        });
        qi.appendChild(row);
        if (saved[i]) {
          row.querySelectorAll(".qopt").forEach(function (x, j) {
            if (j === correct) x.classList.add("right");
            else if (opts[j] === saved[i].chosen) x.classList.add("wrong");
          });
          reveal(saved[i].ok, saved[i].chosen, false);
        }
      } else {
        var row2 = h("div", "qshort");
        var inp = h("input");
        inp.type = "text";
        inp.placeholder = "답을 쓰고 Enter";
        inp.autocomplete = "off";
        var check = button("확인", "primary", function () {
          if (qi.classList.contains("answered")) return;
          var v = norm(inp.value);
          if (!v) return;
          var ok = it.a.some(function (a) {
            return norm(a) === v;
          });
          inp.disabled = true;
          reveal(ok, inp.value, true);
        });
        inp.addEventListener("keydown", function (e) {
          if (e.key === "Enter") check.click();
        });
        row2.appendChild(inp);
        row2.appendChild(check);
        qi.appendChild(row2);
        if (saved[i]) {
          inp.value = saved[i].chosen || "";
          inp.disabled = true;
          reveal(saved[i].ok, saved[i].chosen, false);
        }
      }
      qi.appendChild(why);
      body.appendChild(qi);
    });
    var foot = h("div", "quiz-foot");
    foot.appendChild(h("span", "", kind === "check" ? "이해를 점검하는 가벼운 문제예요. 틀려도 괜찮습니다." : "틀린 문제는 그 장의 요점으로 돌아가 확인하세요. 결과는 이 브라우저에만 남습니다."));
    foot.appendChild(
      button("다시 풀기", "ghost", function () {
        store(key, null);
        box.innerHTML = "";
        renderQuiz(box);
      })
    );
    box.appendChild(foot);
    updateScore();
  }

  // ---------- 질문 패널: 읽다가 바로 적고, 지난 질문을 보고, 답 받는 법을 안내한다 ----------
  function parseQuestions(md) {
    // "### 질문 · 10/23 19:55" 단위로 나눈다
    var out = [];
    var parts = (md || "").split(/\n(?=### )/);
    parts.forEach(function (p) {
      var m = p.match(/^### (질문|요청)[^\n]*·\s*([^\n]+)\n([\s\S]*)$/);
      if (!m) return;
      var body = m[3].trim();
      var quote = "";
      var qm = body.match(/^> ([^\n]+)\n\n?/);
      if (qm) {
        quote = qm[1];
        body = body.slice(qm[0].length).trim();
      }
      out.push({ kind: m[1], when: m[2].trim(), quote: quote, text: body });
    });
    return out;
  }
  function setupAskPanel() {
    var steps = document.querySelector(".day-steps[data-day]");
    if (!steps || !LOCAL) return;
    var did = steps.dataset.day;
    var dn = parseInt(did.slice(1), 10);
    var qname = did + "-questions";

    var fab = h("button", "");
    fab.id = "ask-fab";
    fab.type = "button";
    fab.innerHTML = "<span class='fab-icon'>?</span> Claude에게 질문";
    var panel = h("div");
    panel.id = "ask-panel";

    // 탭: 새 질문 / 지난 질문
    var tabs = h("div", "ap-tabs");
    var tabNew = button("새 질문", "ap-tab on", function () {
      show("new");
    });
    var tabList = button("지난 질문", "ap-tab", function () {
      show("list");
    });
    tabs.appendChild(tabNew);
    tabs.appendChild(tabList);
    tabs.appendChild(
      button("닫기", "ghost ap-close", function () {
        panel.classList.remove("show");
      })
    );
    panel.appendChild(tabs);

    // 새 질문
    var viewNew = h("div", "ap-view");
    var quote = h("div", "ap-quote");
    viewNew.appendChild(quote);
    var ta = h("textarea");
    ta.placeholder = "본문을 드래그해 두고 버튼을 누르면 그 부분이 인용됩니다. 막힌 곳, 모르는 용어, 또는 고치고 싶은 점을 쓰세요.";
    viewNew.appendChild(ta);
    var kind = h("div", "ap-kind");
    kind.innerHTML =
      '<label><input type="radio" name="ap-kind" value="q" checked> 내용 질문</label>' +
      '<label><input type="radio" name="ap-kind" value="r"> 디자인·내용 수정 요청</label>';
    viewNew.appendChild(kind);
    var foot = h("div", "ap-foot");
    foot.appendChild(button("저장", "primary", save));
    viewNew.appendChild(foot);
    panel.appendChild(viewNew);

    // 지난 질문
    var viewList = h("div", "ap-view");
    viewList.style.display = "none";
    var list = h("div", "ap-list");
    viewList.appendChild(list);
    var goto = h("a", "ap-goto", "이 페이지 아래 '질문' 칸과 Claude의 답 보기 ↓");
    goto.href = "#questions";
    goto.addEventListener("click", function () {
      panel.classList.remove("show");
    });
    viewList.appendChild(goto);
    panel.appendChild(viewList);

    // 답 받는 법
    var how = h("div", "ap-how");
    how.innerHTML =
      "<b>답을 받는 법</b><ol><li>저장하면 <code>answers/" +
      qname +
      ".md</code>에 쌓입니다.</li><li>Claude Code 채팅에서 <b>\"D" +
      dn +
      " 질문 답해줘\"</b>라고 말합니다. (수정 요청은 \"요청 반영해줘\")</li><li>답은 이 페이지 맨 아래 '질문' 칸 밑에 질문과 함께 나타납니다.</li></ol>" +
      "<button type='button' class='sbtn tagbtn' data-copy='D" + dn + " 질문 답해줘'>\"D" + dn + " 질문 답해줘\" 복사</button>";
    panel.appendChild(how);
    how.querySelector("[data-copy]").addEventListener("click", function (e) {
      var t = e.currentTarget.dataset.copy;
      try {
        navigator.clipboard.writeText(t);
        toast("복사했어요. Claude Code 채팅에 붙여넣으세요.");
      } catch (err) {
        toast(t);
      }
    });

    function show(which) {
      viewNew.style.display = which === "new" ? "" : "none";
      viewList.style.display = which === "list" ? "" : "none";
      tabNew.classList.toggle("on", which === "new");
      tabList.classList.toggle("on", which === "list");
      if (which === "list") refreshList();
    }
    function refreshList() {
      list.innerHTML = "";
      loadContent(qname).then(function (d) {
        var qs = parseQuestions(d && d.content);
        var qaSec = document.querySelector(".qa-block");
        var answeredStamps = qaSec ? qaSec.innerText : "";
        if (!qs.length) {
          list.appendChild(h("div", "ap-empty", "아직 저장한 질문이 없어요."));
          return;
        }
        qs.reverse().forEach(function (q) {
          var it = h("div", "ap-item");
          var top = h("div", "ap-item-top");
          top.appendChild(h("span", "ap-when", q.when));
          var answered = answeredStamps.indexOf(q.when) >= 0;
          top.appendChild(h("span", "ap-state " + (answered ? "done" : "wait"), answered ? "답변 있음" : "답변 대기"));
          it.appendChild(top);
          if (q.quote) it.appendChild(h("div", "ap-item-quote", "“" + q.quote.slice(0, 80) + (q.quote.length > 80 ? "…" : "") + "”"));
          it.appendChild(h("div", "ap-item-text", q.text.slice(0, 160) + (q.text.length > 160 ? "…" : "")));
          list.appendChild(it);
        });
      });
    }
    function openPanel() {
      panel.classList.toggle("show");
      if (!panel.classList.contains("show")) return;
      var sel = String(window.getSelection && window.getSelection()).trim();
      quote.textContent = sel ? "인용: " + sel.slice(0, 400) : "";
      quote.style.display = sel ? "" : "none";
      panel._sel = sel;
      show("new");
      ta.focus();
    }
    function save() {
      var text = ta.value.trim();
      if (!text) {
        ta.focus();
        return;
      }
      var isReq = panel.querySelector('input[name="ap-kind"]:checked').value === "r";
      var name = isReq ? "requests" : qname;
      var stamp = fmtTime(new Date().toISOString());
      var entry =
        "\n\n### " +
        (isReq ? "요청" : "질문") +
        " · " +
        (isReq ? "D" + dn + " · " : "") +
        stamp +
        "\n" +
        (panel._sel ? "> " + panel._sel.replace(/\n+/g, " ").slice(0, 600) + "\n\n" : "") +
        text +
        "\n";
      loadContent(name)
        .then(function (d) {
          var content = ((d && d.content) || "").replace(/\s+$/, "") + entry;
          return api("answers/" + name, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: content }),
          }).then(function () {
            return content;
          });
        })
        .then(function (content) {
          ta.value = "";
          panel._sel = "";
          quote.style.display = "none";
          toast(
            isReq
              ? "요청을 저장했어요. Claude Code에서 \"요청 반영해줘\"라고 말하면 처리합니다."
              : "질문을 저장했어요. Claude Code에서 \"D" + dn + " 질문 답해줘\"라고 말하면 답이 이 페이지 아래에 붙습니다.",
            true
          );
          var ed = EDITORS[name];
          if (ed) {
            ed.content = content;
            ed.updated = new Date().toISOString();
            FILES[name] = ed.updated;
            ed.renderView();
          }
          show("list");
        })
        .catch(function (err) {
          toast("저장하지 못했어요: " + err.message, true);
        });
    }
    fab.addEventListener("click", openPanel);
    document.body.appendChild(fab);
    document.body.appendChild(panel);
  }

  // ---------- 근거 표기를 참고문헌 페이지로 연결 ----------
  function setupSrcLinks() {
    document.querySelectorAll("span.src").forEach(function (sp) {
      if (sp.closest("a")) return;
      var a = h("a", "src-link");
      a.href = OFFSET + "ledger/references.html";
      a.title = "참고문헌 페이지에서 서지·DOI 보기";
      sp.parentNode.insertBefore(a, sp);
      a.appendChild(sp);
    });
  }

  // ---------- 공개 사이트에서 빠진 원문 그림 자리 ----------
  function setupPaperFigs() {
    document.querySelectorAll("figure.fig.paper img").forEach(function (img) {
      function gone() {
        var ph = h("div", "paper-missing", "원문 그림은 저작권 때문에 공개 사이트에서 빠집니다. 캡션의 저널 링크에서 원문을 볼 수 있습니다.");
        img.replaceWith(ph);
      }
      if (img.complete && img.naturalWidth === 0) gone();
      else img.addEventListener("error", gone);
    });
  }

  // ---------- 시작 ----------
  if (document.querySelector('section.hero')) document.body.classList.add('home');
  setupBrand();
  setupPaperFigs();
  setupFontSize();
  setupProgressBar();
  Promise.all([detectMode(), deps()])
    .then(loadStatus)
    .then(function () {
      var els = Array.prototype.slice.call(document.querySelectorAll(".editable[data-file]"));
      return Promise.all(
        els.map(function (el) {
          return new Editable(el).init();
        })
      );
    })
    .then(function () {
      setupStepChecks();
      applyStatus();
      setupGates();
      setupReadMode();
      setupToday();
      setupComments();
      setupChapters();
      setupQuiz();
      setupAskPanel();
      setupSrcLinks();
    });
})();
