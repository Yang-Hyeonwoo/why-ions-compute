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
    ["[계산]", "tag-calc", "계산"],
    ["[가정]", "tag-assume", "가정"],
  ];

  var LOCAL = false;
  // 움직임 줄이기 설정을 켠 사람에게는 부드러운 스크롤도 끈다
  var SMOOTH = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
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
  // 브라우저 임시 저장. 실패하면 성공처럼 넘어가지 않고 한 번 알린다.
  var STORE_WARNED = false;
  function store(key, value) {
    try {
      if (value == null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
      return true;
    } catch (e) {
      if (!STORE_WARNED) {
        STORE_WARNED = true;
        setTimeout(function () {
          toast("이 브라우저에 기록을 저장하지 못했어요(사생활 보호 창이거나 저장 공간이 꽉 찼을 수 있어요). 퀴즈·실습 기록이 남지 않습니다.", true);
        }, 0);
      }
      return false;
    }
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
      t.setAttribute("role", "status");
      t.setAttribute("aria-live", "polite");
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
      self.rev = (data && data.rev) || null;
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
    ta.setAttribute("aria-label", this.title + " 쓰기");
    self._ta = ta;
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
    this.el.scrollIntoView({ behavior: SMOOTH, block: "start" });
  };
  Editable.prototype.save = function (text, btn, force) {
    var self = this;
    if (self.saving) return; // 저장 중 중복 클릭 방지
    var content = text.replace(/\r\n/g, "\n");
    self.saving = true;
    function done() {
      self.saving = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "초안 저장";
      }
    }
    if (btn) {
      btn.disabled = true;
      btn.textContent = "저장 중…";
    }
    var body = { content: content, base_rev: self.rev || null };
    if (force) body.force = true;
    fetch("/api/answers/" + this.name, {
      method: "PUT",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(
        function (r) {
          return r.json().then(function (j) {
            return { status: r.status, j: j };
          });
        },
        function () {
          throw new Error("서버에 연결할 수 없어요. 사이트 서버가 꺼졌는지 확인하세요.");
        }
      )
      .then(function (res) {
        done();
        if (res.status === 409) {
          var when = res.j.updated ? fmtTime(res.j.updated) : "";
          store("study-draft:" + self.name, text);
          if (confirm("이 칸은 다른 탭(또는 창)에서 " + when + "에 먼저 저장되었습니다.\n\n확인: 지금 쓴 글로 덮어쓰기 (앞 버전은 수정 이력에 남습니다)\n취소: 저장하지 않기 (지금 쓴 글은 임시 글로 남습니다)")) {
            self.rev = res.j.rev;
            return self.save(text, btn, true);
          }
          toast("저장하지 않았어요. 쓴 글은 임시 글로 남아 있어요. 새로고침하면 최신 버전을 보고 임시 글을 불러올 수 있어요.", true);
          return;
        }
        if (res.status !== 200 || !res.j.ok) throw new Error(res.j.error || res.status);
        var j = res.j;
        self.content = content;
        self.updated = j.updated;
        self.rev = j.rev;
        if (content.trim()) FILES[self.name] = j.updated;
        else delete FILES[self.name];
        var ta = self._ta;
        var typedMore = ta && document.body.contains(ta) && ta.value.replace(/\r\n/g, "\n") !== content;
        if (typedMore) {
          // 저장하는 동안 더 쓴 내용은 편집기에 그대로 두고 임시 글로 보관
          self.dirty = true;
          store("study-draft:" + self.name, ta.value);
          toast("저장했어요. 저장하는 동안 더 쓴 내용은 아직 저장 전이에요.", true);
          return;
        }
        store("study-draft:" + self.name, null);
        self.renderView();
        if (j.history_error) toast("저장했어요. 다만 수정 이력(git) 기록은 실패했어요: " + j.history_error, true);
        else toast(j.committed ? "초안을 저장했어요 · 수정 이력에 남겼어요" : "초안을 저장했어요");
      })
      .catch(function (err) {
        done();
        store("study-draft:" + self.name, text);
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

  // ---------- 용어의 영어 원어 ----------
  // 논문은 영어로 읽게 되므로, 번역 용어가 페이지에서 처음 나올 때 원어를 괄호로 붙인다(assets/glossary.json).
  // 이미 괄호가 붙은 곳, 수식·코드·링크·제목·퀴즈 안은 건드리지 않는다.
  function setupGlossary() {
    var root = document.querySelector(".lesson-body") || document.querySelector(".unit-head");
    if (!root || !window.fetch) return;
    var unit = (document.querySelector(".day-steps") || {}).dataset ? document.querySelector(".day-steps").dataset.day : "";
    fetch(OFFSET + "assets/glossary.json")
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (g) {
        if (!g) return;
        var terms = g.terms
          .filter(function (t) {
            return !t.only || new RegExp(t.only).test(unit || "");
          })
          .map(function (t) {
            var re;
            try {
              re = new RegExp(t.pat || t.ko.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
            } catch (e) {
              return null;
            }
            return { t: t, re: re };
          })
          .filter(Boolean)
          .sort(function (a, b) {
            return b.t.ko.length - a.t.ko.length;
          });
        var SKIP = "code, pre, a, h1, h2, h3, h4, h5, h6, script, style, svg, .math, mjx-container, .katex, .quiz, .prov, .src, .gl-en, summary, .paper-note, .day-steps, button, textarea, .editable, .qa-block, .comments";
        var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
          acceptNode: function (n) {
            if (!n.nodeValue || n.nodeValue.length < 2) return NodeFilter.FILTER_REJECT;
            if (/\$|\\\(|\\\[/.test(n.nodeValue)) return NodeFilter.FILTER_REJECT;
            var p = n.parentElement;
            return p && !p.closest(SKIP) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
          },
        });
        var nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        // 문장 속 괄호 안('새는 전류(누설)')에 든 용어에는 괄호를 겹쳐 붙이지 않는다
        function insideParen(v, at) {
          var open = (v.slice(0, at).match(/[(（]/g) || []).length,
            close = (v.slice(0, at).match(/[)）]/g) || []).length;
          return open > close;
        }
        terms.forEach(function (x) {
          var firstWord = x.t.en.split(/[ ,/(]/)[0].toLowerCase();
          var re = new RegExp(x.re.source, "g");
          for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i],
              v = n.nodeValue,
              m = null,
              hit = null,
              stop = false;
            re.lastIndex = 0;
            while ((m = re.exec(v))) {
              var e = m.index + m[0].length;
              // 바로 뒤에 이미 괄호(원어)가 있거나 영어가 이어지면 붙이지 않고 이 용어는 끝낸다
              var after = v.slice(e, e + 40);
              if (after.length < 40) {
                // 굵은 글씨 끝처럼 노드가 끝나면 문서 순서로 이어지는 글자까지 본다
                var tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                tw.currentNode = n;
                while (after.length < 40 && tw.nextNode()) after += tw.currentNode.nodeValue;
              }
              if (/^\s*["'”’」』]?\s*[(（]/.test(after) ||after.toLowerCase().indexOf(firstWord) >= 0) {
                stop = true;
                break;
              }
              if (insideParen(v, m.index) || /^\s*[)）]/.test(after)) continue;
              hit = e;
              break;
            }
            if (stop) break;
            if (hit === null) continue;
            var end = hit;
            var tail = n.splitText(end);
            var sp = document.createElement("span");
            sp.className = "gl-en";
            sp.textContent = "(" + x.t.en + ")";
            if (x.t.def) sp.title = x.t.def;
            n.parentNode.insertBefore(sp, tail);
            nodes.splice(i + 1, 0, tail);
            break;
          }
        });
      })
      .catch(function () {});
  }

  // ---------- 핵심 문장 구별 ----------
  // 문단 첫머리의 굵은 이름표("**무엇을 볼지.**")는 이름표 모양으로, 문장 속 굵은 글씨는 형광펜처럼 보이게 나눈다.
  function setupEmphasis() {
    document.querySelectorAll(".lesson-body p > strong:first-child, .lesson-body li > strong:first-child").forEach(function (b) {
      var prev = b.previousSibling;
      if (prev && prev.nodeType === 3 && prev.nodeValue.trim()) return;
      if (/[.:：]\s*$/.test(b.textContent) && b.textContent.length <= 40) b.classList.add("lead-in");
    });
    // 본문 문단 속 굵은 핵심어에 옅은 형광펜(.key 핵심 문장은 진한 형광펜 그대로). 문단 첫머리의 소제목성 굵은 글씨·상자·표·퀴즈 안은 제외.
    document.querySelectorAll(".lesson-body p strong").forEach(function (b) {
      if (b.classList.contains("lead-in") || b.closest(".key, .callout, details, table, .quiz, .prov, .src, .stepper, figure, .done-box")) return;
      var t = b.textContent.trim();
      if (t.length < 2 || t.length > 40) return;
      var prev = b.previousSibling;
      if (b.parentNode.firstChild === b || (prev && prev.nodeType === 3 && !prev.nodeValue.trim() && prev === b.parentNode.firstChild)) return;
      b.classList.add("hl-soft");
    });
  }

  // ---------- 학습 단위 상태 ----------
  // 키: 학습 단위 id(d01a, d01b, d05 …). 원래 Day(dNN)의 기록(답 파일·퀴즈·사전 테스트 점수)은 Day 키에 그대로 있다.
  // 원래 Day를 둘로 나눈 단위는, 나누기 전에 Day 전체에 남긴 완료·읽음·복습 기록을 두 단위 모두 이어 받는다.
  function srcOf(key) {
    return String(key).slice(0, 3);
  }
  function isSplit(key) {
    return /^d\d\d[ab]$/.test(key);
  }
  function pageStatus(key) {
    if (!isSplit(key)) return DAYS[key] || {};
    var old = DAYS[srcOf(key)] || {},
      out = {};
    ["done", "lesson", "reviews"].forEach(function (k) {
      if (old[k]) out[k] = old[k];
    });
    if (old.done) out.inherited = true;
    var cur = DAYS[key] || {};
    Object.keys(cur).forEach(function (k) {
      out[k] = cur[k];
    });
    if (cur.done) delete out.inherited;
    return out;
  }
  // 세부 기록으로 판단할 수 없는 예전 기록(사전 테스트 점수·회상·답 파일)이 있는가: 숙달로 보지 않고 '기존 기록 있음'으로만 알린다
  function legacyNote(key) {
    var src = srcOf(key),
      d = DAYS[src] || {},
      bits = [];
    if (d.pretest) bits.push("사전 테스트");
    if (d.posttest) bits.push("다시 풀기");
    if (FILES[src + "-recall"] || d.recall) bits.push("백지 회상");
    if (FILES[src + "-answer"]) bits.push("내 답");
    if (FILES[src + "-questions"]) bits.push("질문");
    return bits;
  }
  function visited(key) {
    try {
      return Object.keys(JSON.parse(recall("study-visited:" + key) || "{}")).length > 0;
    } catch (e) {
      return false;
    }
  }
  // done: '학습 완료'를 누름 / started: 읽기 시작했거나 기록이 있음 / "": 학습 전
  function dayState(key) {
    var st = pageStatus(key);
    if (st.done) return "done";
    if (st.lesson || st.note || visited(key) || legacyNote(key).length) return "started";
    return "";
  }
  var STATE_NAME = { done: "완료", started: "학습 중", "": "학습 전" };
  var STATE_ICON = { done: "✓", started: "◐", "": "○" };
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
      el.setAttribute("aria-label", (el.getAttribute("title") || "") + " · " + STATE_NAME[st]);
      // 2회독 이상이면 로드맵 카드에 작은 ×N 표시
      var rc = readCount(el.dataset.day),
        badge = el.querySelector(".rm-reads");
      if (rc >= 2 && el.classList.contains("rm-day")) {
        if (!badge) {
          badge = h("span", "rm-reads");
          el.appendChild(badge);
        }
        badge.textContent = rc + "회독";
      } else if (badge) badge.remove();
    });
    document.querySelectorAll(".day-status[data-day]").forEach(function (el) {
      var st = dayState(el.dataset.day);
      el.textContent = STATE_ICON[st] + " " + STATE_NAME[st];
      el.className = "day-status" + (st ? " st-" + st : "");
    });
    document.querySelectorAll("#quarto-sidebar a.sidebar-link").forEach(function (a) {
      var m = (a.getAttribute("href") || "").match(/days\/(d\d\d[ab]?)\.html/);
      if (!m) return;
      var old = a.querySelector(".sb-dot");
      if (old) old.remove();
      var st = dayState(m[1]);
      if (!st) return;
      var text = a.querySelector(".sidebar-item-text") || a;
      var dot = h("span", "sb-dot st-" + st, STATE_ICON[st]);
      dot.title = STATE_NAME[st];
      text.appendChild(dot);
    });
    document.querySelectorAll(".day-steps[data-day]").forEach(function (ol) {
      var key = ol.dataset.day,
        st = pageStatus(key);
      var map = { lesson: !!st.lesson || visited(key), done: !!st.done, review: !!document.querySelector(".quiz-review .qitem.answered") };
      ol.querySelectorAll("li").forEach(function (li) {
        li.classList.toggle("done", !!map[li.dataset.step]);
      });
    });
    document.querySelectorAll(".done-box[data-day]").forEach(function (box) {
      var key = box.dataset.day,
        d = pageStatus(key),
        s0 = dayState(key);
      box.classList.toggle("is-done", s0 === "done");
      var stEl = box.querySelector(".done-state");
      if (stEl) {
        stEl.innerHTML = "";
        stEl.appendChild(h("span", "ds-icon st-" + (s0 || "none"), STATE_ICON[s0]));
        stEl.appendChild(h("b", "", STATE_NAME[s0]));
        if (s0 === "done")
          stEl.appendChild(
            h("span", "ds-when", d.inherited ? " · 나누기 전 원래 Day의 완료 기록(" + fmtTime(d.done) + ")을 이어 받음" : " · " + fmtTime(d.done))
          );
        var legacy = legacyNote(key);
        if (legacy.length && s0 !== "done") stEl.appendChild(h("span", "ds-when", " · 기존 학습 기록 있음(" + legacy.join(", ") + ") — 완료 여부는 직접 표시하세요"));
      }
      readsRow(box, key, d, s0);
      var doneBtn = box.querySelector('[data-action="done"]'),
        undoneBtn = box.querySelector('[data-action="undone"]');
      if (doneBtn) doneBtn.style.display = s0 === "done" ? "none" : "";
      if (undoneBtn) undoneBtn.style.display = s0 === "done" ? "" : "none";
      var stc = box.querySelector(".done-static");
      if (stc) stc.textContent = s0 === "done" ? "학습 완료 " + fmtTime(d.done) : "";
      // 퀴즈 결과는 완료와 따로 보여 준다
      var sum = box.querySelector(".done-summary");
      if (!sum) {
        sum = h("div", "done-summary");
        box.appendChild(sum);
      }
      var firsts = {};
      try {
        firsts = JSON.parse(recall("study-first:" + srcOf(key)) || "{}");
      } catch (e) {}
      var ids = {};
      box.closest("main, body").querySelectorAll(".quiz[data-set]").forEach(function (q) {
        if (q.dataset.set !== "pre") ids[q.dataset.set] = 1;
      });
      var fk = Object.keys(firsts),
        fok = fk.filter(function (k) {
          return firsts[k].ok;
        }).length;
      sum.textContent = fk.length ? "퀴즈 첫 시도 기록(원래 Day 전체): " + fok + " / " + fk.length + "문항 정답 · 완료와는 따로 기록됩니다" : "";
    });
  }
  // 회독: 첫 완료가 1회독, 다시 읽고 끝낼 때마다 reads에 시각이 하나씩 붙는다(2회독, 3회독…). 완료·퀴즈와는 따로.
  function readCount(key) {
    var st = pageStatus(key);
    return st.done ? 1 + (st.reads || []).length : 0;
  }
  function readsRow(box, key, d, s0) {
    var row = box.querySelector(".done-reads");
    if (!row) {
      row = h("div", "done-reads");
      var st = box.querySelector(".done-state");
      st.parentNode.insertBefore(row, st.nextSibling);
    }
    row.innerHTML = "";
    if (s0 !== "done") return;
    var reads = d.reads || [];
    var chips = h("div", "rd-chips");
    chips.appendChild(h("span", "rd-chip", "1회독 · " + fmtTime(d.done).split(" ")[0]));
    reads.forEach(function (at, i) {
      chips.appendChild(h("span", "rd-chip", i + 2 + "회독 · " + fmtTime(at).split(" ")[0]));
    });
    row.appendChild(chips);
    if (!LOCAL) return;
    var acts = h("div", "rd-acts");
    function send(op) {
      acts.querySelectorAll("button").forEach(function (b) {
        b.disabled = true;
      });
      setDayStatus(key, { reads: op }).catch(function (err) {
        toast("저장하지 못했어요: " + err.message, true);
        applyStatus();
      });
    }
    acts.appendChild(button("+ " + (reads.length + 2) + "회독 완료", "ghost", function () {
      send("add");
    }));
    if (reads.length)
      acts.appendChild(button("마지막 회독 취소", "ghost lab-small", function () {
        send("pop");
      }));
    row.appendChild(acts);
  }
  function setupStepChecks() {
    document.querySelectorAll(".done-box[data-day]").forEach(function (box) {
      var key = box.dataset.day,
        src = srcOf(key);
      var doneBtn = box.querySelector('[data-action="done"]');
      var undoneBtn = box.querySelector('[data-action="undone"]');
      var msg = box.querySelector(".done-msg");
      if (!doneBtn || !undoneBtn) return;
      function busy(on) {
        doneBtn.disabled = undoneBtn.disabled = on;
        if (on && msg) {
          msg.className = "done-msg";
          msg.textContent = "저장하는 중…";
        }
      }
      function fail(err, retry) {
        busy(false);
        if (!msg) return toast("저장하지 못했어요: " + err.message, true);
        msg.className = "done-msg is-error";
        msg.innerHTML = "";
        msg.appendChild(h("span", "", "⚠ 저장하지 못했어요(" + err.message + "). 화면의 표시는 바뀌지 않았습니다. 사이트를 연 창(사이트열기)이 켜져 있는지 확인한 뒤 "));
        msg.appendChild(button("다시 시도", "ghost lab-small", retry));
      }
      function ok(text) {
        busy(false);
        if (msg) {
          msg.className = "done-msg is-ok";
          msg.textContent = text;
        }
      }
      function markDone() {
        busy(true);
        setDayStatus(key, { done: true })
          .then(function () {
            ok("✓ 학습 완료로 저장했어요. 다음 학습은 아래 링크에서 이어 가세요.");
          })
          .catch(function (err) {
            fail(err, markDone);
          });
      }
      function markUndone() {
        busy(true);
        var chain = Promise.resolve();
        // 나누기 전 원래 Day의 완료 기록이 남은 단위(이어 받았든, 새 완료와 함께 있든): 짝 단위의 완료는 원래 시각 그대로 남기고,
        // 원래 Day의 완료를 지워야 이 단위의 완료가 되살아나지 않는다
        if (isSplit(key) && (DAYS[src] || {}).done) {
          var sib = src + (key.slice(-1) === "a" ? "b" : "a");
          var oldDone = (DAYS[src] || {}).done;
          chain = chain
            .then(function () {
              return (DAYS[sib] || {}).done ? null : setDayStatus(sib, { done: oldDone });
            })
            .then(function () {
              return setDayStatus(src, { done: false });
            });
        }
        chain
          .then(function () {
            return setDayStatus(key, { done: false });
          })
          .then(function () {
            ok("학습 중으로 되돌렸어요.");
          })
          .catch(function (err) {
            fail(err, markUndone);
          });
      }
      doneBtn.addEventListener("click", markDone);
      undoneBtn.addEventListener("click", markUndone);
    });
  }

  // ---------- 학습자료 가리개 ----------
  function setupGates() {
    if (!LOCAL) return;
    document.querySelectorAll(".lesson-body[data-pre]").forEach(function (lb) {
      var pre = lb.dataset.pre;
      var did = pre.replace(/-pre$/, "");
      var hasPretest = !!document.querySelector('.quiz[data-day="' + did + '"][data-set="pre"]:not([data-mode])');
      if (recall("study-pre-done:" + did) || (DAYS[did] || {}).pretest || recall("study-gate-open:" + pre)) return;
      if (!hasPretest && FILES[pre]) return;
      if (lb.querySelector(".gate")) return;
      lb.classList.add("gated");
      var gate = h("div", "gate");
      var p = h("p");
      p.innerHTML = hasPretest
        ? "<b>사전 테스트를 먼저 풀어 볼까요?</b><br>아직 배우지 않았으니 많이 틀리는 게 정상입니다. 먼저 답해 본 문제는 읽을 때 눈에 들어오고 더 오래 남습니다. 다 풀면 자료가 열립니다."
        : "<b>'먼저 만들어 보기'를 먼저 해 볼까요?</b><br>자료를 보기 전에 지금 아는 만큼 써 두면, 공부가 끝난 뒤 무엇을 배웠는지 보입니다.";
      gate.appendChild(p);
      var row = h("div", "btn-row");
      row.appendChild(
        button(hasPretest ? "사전 테스트로 가기" : "먼저 해 보기 쓰기", "primary", function () {
          var t = document.getElementById("pretest");
          if (t) t.scrollIntoView({ behavior: SMOOTH, block: "start" });
          else if (EDITORS[pre]) EDITORS[pre].startEdit();
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
  document.addEventListener("study:pre-done", function (e) {
    var lb = document.querySelector('.lesson-body[data-pre="' + e.detail.day + '-pre"]');
    if (lb && lb.classList.contains("gated")) {
      ungate(lb);
      toast("자료가 열렸어요. 틀린 문제의 답을 찾으며 읽어 보세요.");
    }
    applyStatus();
  });
  function ungate(lb) {
    lb.classList.remove("gated");
    var g = lb.querySelector(".gate");
    if (g) g.remove();
  }
  document.addEventListener("study:changed", function () {
    applyStatus();
    document.querySelectorAll(".lesson-body.gated").forEach(function (lb) {
      var hasPretest = !!document.querySelector('.quiz[data-set="pre"]:not([data-mode])');
      if (FILES[lb.dataset.pre] && !hasPretest) ungate(lb);
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

  // ---------- 커버 페이지: 다음 Day, 이어서 하기, 날짜에 맞춘 작은 복습 ----------
  // Day는 마감이 아니라 순서다. 밀린 날 목록 대신 "다음에 할 것"과 "지금 복습할 것"만 보여 준다.
  var REVIEW_GAPS = [1, 3, 7, 14, 30]; // 학습 완료 뒤 며칠째에 핵심 목록을 다시 떠올릴지 (조정 가능한 규칙)
  function daysBetween(isoA, isoB) {
    var a = new Date(isoA.slice(0, 10) + "T00:00:00"),
      b = new Date(isoB.slice(0, 10) + "T00:00:00");
    return Math.round((b - a) / 86400000);
  }
  function dueReviews(days) {
    var today = todayIso(),
      out = [];
    days.forEach(function (d) {
      var st = pageStatus(d.day);
      if (!st.done) return;
      var since = daysBetween(st.done, today);
      var rv = st.reviews || {};
      // 아직 하지 않은 간격 중 이미 때가 된 가장 큰 간격 하나만 낸다(밀린 복습을 한꺼번에 쌓지 않음)
      var gap = null;
      REVIEW_GAPS.forEach(function (g) {
        if (since >= g && !rv[String(g)]) gap = g;
      });
      if (gap !== null) out.push({ d: d, gap: gap, since: since });
    });
    out.sort(function (x, y) {
      return y.since - x.since;
    });
    return out;
  }
  // 학습 단위 k의 핵심 복습 퀴즈는 다음 단위 맨 앞(#review)에 있다. 마지막 단위는 그 단위의 총정리 바로 뒤 종합 퀴즈로.
  function reviewHref(days, d) {
    var nx = days[d.n];
    return OFFSET + "days/" + (nx && nx.hasReview ? nx.day + ".html#review" : d.day + ".html#wrapup");
  }
  function reviewLabel(days, d) {
    var nx = days[d.n];
    return "Day " + d.n + " · " + d.title + (nx && nx.hasReview ? "" : " (총정리와 종합 퀴즈)");
  }
  // 홈의 간격 회상: 완료한 단위 페이지에서 퀴즈 데이터를 읽어, 그 단위에 나온 점검·종합 문항 중 셋을 이 자리에 낸다.
  // 이미 본 답이 펼쳐진 채로 나오지 않도록 날짜마다 새 세트 이름을 쓴다(첫 시도 기록은 문항 id로 이어진다).
  function recallHere(d, slot) {
    if (slot.firstChild) {
      slot.innerHTML = "";
      return;
    }
    slot.appendChild(h("div", "tc-rv-note", "불러오는 중…"));
    fetch(OFFSET + "days/" + d.day + ".html")
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var dataEl = doc.getElementById("quiz-" + d.src);
        if (!dataEl) throw new Error("퀴즈 없음");
        var data = JSON.parse(dataEl.textContent);
        var here = {};
        doc.querySelectorAll(".quiz[data-set]").forEach(function (q) {
          if (!q.dataset.mode) here[q.dataset.set] = 1;
        });
        // 문항의 ref(#앵커, dXX.html#…)와 fig(../assets/…)는 단위 페이지 기준이라, 홈에서 쓰도록 그 페이지 주소로 바꾼다.
        // 이 쪽에 없는 앵커(나뉜 Day의 다른 쪽)는 단위 페이지에서처럼 링크를 달지 않는다.
        var pageUrl = new URL(OFFSET + "days/" + d.day + ".html", location.href).href;
        function rebase(it) {
          var c = JSON.parse(JSON.stringify(it));
          if (c.ref && c.ref.charAt(0) === "#") {
            var ok = false;
            try {
              ok = !!doc.querySelector(c.ref);
            } catch (e) {}
            if (ok) c.ref = pageUrl + c.ref;
            else delete c.ref;
          } else if (c.ref) c.ref = new URL(c.ref, pageUrl).href;
          if (c.fig) c.fig = new URL(c.fig, pageUrl).href;
          return c;
        }
        var pool = [];
        Object.keys(data.sets || {}).forEach(function (k) {
          var st = data.sets[k];
          if (!here[k] || /^review/.test(k) || st.kind === "pre") return;
          (st.items || []).forEach(function (it) {
            if ((it.type === "mc" || it.type === "ox") && it.id && !pool.some(function (x) { return x.id === it.id; })) pool.push(rebase(it));
          });
        });
        if (!pool.length) throw new Error("문항 없음");
        for (var i = pool.length - 1; i > 0; i--) {
          var j = Math.floor(Math.random() * (i + 1)),
            t = pool[i];
          pool[i] = pool[j];
          pool[j] = t;
        }
        // 같은 원본의 a/b 단위 복습을 함께 열어도 세트·저장 키가 섞이지 않게 단위 이름을 넣고, 이미 실린 세트는 지우지 않고 합친다.
        var setId = "recall-" + d.day + "-" + todayIso();
        var old = document.getElementById("quiz-" + d.src);
        if (old) {
          try {
            var prev = JSON.parse(old.textContent).sets || {};
            Object.keys(prev).forEach(function (k) {
              if (/^recall-/.test(k)) data.sets[k] = prev[k];
            });
          } catch (e) {}
          old.remove();
        }
        data.sets[setId] = { kind: "review", title: "Day " + d.n + " 다시 떠올리기", items: pool.slice(0, 3) };
        var sc = document.createElement("script");
        sc.type = "application/json";
        sc.id = "quiz-" + d.src;
        sc.textContent = JSON.stringify(data);
        document.body.appendChild(sc);
        slot.innerHTML = "";
        var box = h("div", "quiz");
        box.dataset.day = d.src;
        box.dataset.set = setId;
        slot.appendChild(box);
        renderQuiz(box);
        typeset(box);
      })
      .catch(function (e) {
        slot.innerHTML = "";
        slot.appendChild(h("div", "tc-rv-note", "문제를 불러오지 못했어요(" + e.message + "). 위 링크로 가서 복습해 주세요."));
      });
  }
  // 홈의 '지금까지 쌓은 것': 완료한 단위의 '배울 핵심'을 최근 것부터. 숙달 판정이 아니라 지나온 길의 목록이다.
  function gainsPanel(days) {
    var got = days.filter(function (d) {
      return dayState(d.day) === "done" && d.learn;
    });
    if (!got.length) return null;
    var box = h("details", "tc-gains");
    box.appendChild(h("summary", "", "지금까지 배운 것 · " + got.length + "개 단위"));
    var ul = h("ul");
    got
      .slice()
      .reverse()
      .forEach(function (d) {
        var li = h("li");
        var a = h("a", "", "Day " + d.n);
        a.href = OFFSET + "days/" + d.day + ".html";
        li.appendChild(a);
        li.appendChild(document.createTextNode(" " + d.learn));
        ul.appendChild(li);
      });
    box.appendChild(ul);
    box.appendChild(h("div", "tc-rv-note", "한 줄씩 소리 내어 설명해 보고, 막히는 줄만 그 Day로 돌아가면 됩니다."));
    return box;
  }
  function unitForLast(days, last) {
    if (!last) return null;
    var u = days.find(function (d) {
      return d.day === last.day;
    });
    if (u) return u;
    // 나누기 전 기록(원래 Day 키): 그 장이 있는 단위
    var cands = days.filter(function (d) {
      return d.src === last.day;
    });
    return (
      cands.find(function (d) {
        return (d.chs || []).indexOf(last.id) >= 0;
      }) || cands[0] || null
    );
  }
  // 홈의 두 길(2026-10-31 요청): 주 행동은 '최근 읽던 곳'. 읽던 단위가 완료면 그 바로 다음 미완료 단위.
  // 순서상 앞에 완료 표시가 없는 단위(firstOpen)는 따로 작게 알린다. 기록이 없으면 첫 미완료 단위.
  function currentUnit(days) {
    var open = function (d) {
      return dayState(d.day) !== "done";
    };
    var firstOpen = days.find(open) || null;
    var last = null;
    try {
      last = JSON.parse(recall("study-last-any") || "null");
    } catch (e) {}
    var lastU = unitForLast(days, last);
    var cur = firstOpen,
      resume = false,
      after = null;
    if (lastU && open(lastU)) {
      cur = lastU;
      resume = true;
    } else if (lastU) {
      after = lastU;
      cur = days.slice(days.indexOf(lastU) + 1).find(open) || firstOpen;
    }
    return { cur: cur, last: last, resume: resume, after: after, firstOpen: firstOpen };
  }
  // 가장 최근에 완료로 표시한 단위
  // 완료한 단위 중 가장 뒤의 것(누른 시각이 아니라 순서 기준: 앞 Day를 나중에 몰아서 눌러도 흐름상 마지막을 보인다)
  function lastDone(days) {
    var best = null;
    days.forEach(function (d) {
      if (pageStatus(d.day).done) best = d;
    });
    return best;
  }
  // "학습 구간 1. Day 3–4의 2×2 예제를 전선으로: …" → "2×2 예제를 전선으로: …"
  function chapterText(title) {
    return (title || "")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/^(?:학습 구간\s*)?\d+[.)]\s*/, "")
      .replace(/^Day\s*[\d–-]+의\s*/, "");
  }
  // 로드맵(홈의 작은 지도, 로드맵 페이지): Phase별 완료 수, 지금 위치
  function markRoadmap(days, cur) {
    var done = days.filter(function (d) {
      return dayState(d.day) === "done";
    }).length;
    document.querySelectorAll(".pb-day.is-current").forEach(function (el) {
      el.classList.remove("is-current");
      el.removeAttribute("aria-current");
    });
    if (cur)
      document.querySelectorAll('.pb-day[data-day="' + cur.day + '"]').forEach(function (el) {
        el.classList.add("is-current");
        el.setAttribute("aria-current", "step");
      });
    document.querySelectorAll("[data-phase-count]").forEach(function (el) {
      var ph = parseInt(el.dataset.phaseCount, 10);
      var us = days.filter(function (d) {
        return d.phase === ph;
      });
      var dn = us.filter(function (d) {
        return dayState(d.day) === "done";
      }).length;
      el.textContent = dn + " / " + us.length;
    });
    document.querySelectorAll(".pb-phase[data-phase]").forEach(function (el) {
      var ph = parseInt(el.dataset.phase, 10);
      var us = days.filter(function (d) {
        return d.phase === ph;
      });
      var dn = us.filter(function (d) {
        return dayState(d.day) === "done";
      }).length;
      el.style.setProperty("--done", us.length ? dn / us.length : 0);
      el.classList.toggle("is-complete", us.length > 0 && dn === us.length);
      el.classList.toggle("is-current-phase", !!cur && cur.phase === ph);
    });
    ["hm-stat", "rm-stat"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.textContent = "완료 " + done + " / " + days.length + (cur ? " · 지금 Day " + cur.n : "");
    });
  }
  function setupRoadmap() {
    if (document.getElementById("today-card")) return;
    var dataEl = document.getElementById("study-days");
    if (!dataEl || !document.querySelector(".pb-phase")) return;
    var days = JSON.parse(dataEl.textContent);
    markRoadmap(days, currentUnit(days).cur);
  }
  function setupToday() {
    var card = document.getElementById("today-card");
    var dataEl = document.getElementById("study-days");
    if (!card || !dataEl) return;
    var days = JSON.parse(dataEl.textContent);
    var cu = currentUnit(days),
      cur = cu.cur,
      last = cu.last;
    var anyDone = days.some(function (d) {
      return dayState(d.day) === "done";
    });
    if (anyDone || cu.resume) document.body.classList.add("returning");
    card.innerHTML = "";
    var main = h("div", "tc-main");
    if (cur) {
      main.appendChild(
        h("div", "tc-label", cu.resume ? "최근 읽던 곳" : cu.after ? "최근 학습한 Day " + cu.after.n + " 다음" : anyDone ? "다음 단위" : "처음 시작")
      );
      var t = h("h2", "tc-title");
      t.appendChild(h("span", "tc-day", "Day " + cur.n));
      t.appendChild(h("span", "tc-t", cur.title));
      main.appendChild(t);
      if (cur.q) main.appendChild(h("p", "tc-q", cur.q));
      var chs = cur.chs || [];
      if (chs.length) {
        var seen = {};
        try {
          seen = JSON.parse(recall("study-visited:" + cur.day) || "{}");
        } catch (e) {}
        var at = cu.resume && last && last.id ? chs.indexOf(last.id) : -1;
        var prog = h("div", "tc-prog");
        var segs = h("div", "tc-segs");
        segs.setAttribute("aria-hidden", "true");
        chs.forEach(function (c, i) {
          segs.appendChild(h("i", (seen[c] || i < at ? "seen" : "") + (i === at ? " at" : "")));
        });
        prog.appendChild(segs);
        var where = h("div", "tc-where");
        if (at >= 0) {
          where.appendChild(h("b", "", "구간 " + (at + 1) + " / " + chs.length));
          var ct = chapterText(last.title);
          if (ct) where.appendChild(document.createTextNode(" · " + ct));
        } else {
          where.appendChild(document.createTextNode("학습 구간 " + chs.length + "개"));
        }
        prog.appendChild(where);
        main.appendChild(prog);
      }
      var a = h("a", "sbtn primary tc-go", cu.resume ? "이어서 읽기 →" : "Day " + cur.n + " 시작 →");
      a.href = OFFSET + "days/" + cur.day + ".html" + (cu.resume && last.id ? "#" + last.id : "");
      main.appendChild(a);
      // 순서상 앞에 완료 표시가 없는 단위: 강요하지 않고 한 줄로만
      var fo = cu.firstOpen;
      if (fo && fo !== cur && fo.n < cur.n) {
        var sk = h("p", "tc-skip");
        sk.appendChild(document.createTextNode("순서대로 보면 완료 표시가 없는 앞 단위가 있어요: "));
        var sa = h("a", "", "Day " + fo.n + " · " + fo.title);
        sa.href = OFFSET + "days/" + fo.day + ".html";
        sk.appendChild(sa);
        main.appendChild(sk);
      }
    } else {
      main.appendChild(h("div", "tc-label", "모든 학습 단위를 완료로 표시했습니다"));
      main.appendChild(h("h2", "tc-title", "복습을 이어 가고, 마지막 Day의 결정을 다시 읽어 보세요."));
    }
    card.appendChild(main);

    var side = h("div", "tc-side");
    var due = dueReviews(days);
    if (due.length) {
      var rb = h("div", "tc-review");
      var hd = h("div", "tc-rv-head");
      hd.appendChild(h("span", "tc-mini-label", "다시 떠올려 볼 단위"));
      hd.appendChild(h("span", "tc-rv-hint", "완료하고 며칠 지난 단위예요. 시간이 날 때만, 3문제면 충분합니다."));
      rb.appendChild(hd);
      due.slice(0, 3).forEach(function (r) {
        var row = h("div", "tc-rv-row");
        var info = h("div", "tc-rv-info");
        var ra = h("a", "tc-rv-t");
        ra.href = reviewHref(days, r.d);
        ra.appendChild(h("span", "tc-rv-n", "Day " + r.d.n));
        ra.appendChild(document.createTextNode(r.d.title));
        info.appendChild(ra);
        row.appendChild(info);
        var btns = h("div", "tc-rv-btns");
        var slot = h("div", "tc-recall");
        btns.appendChild(
          button("3문제", "lab-small", function () {
            recallHere(r.d, slot);
          })
        );
        if (LOCAL) {
          btns.appendChild(
            button("떠올려 봄", "ghost lab-small", function () {
              var patch = { reviews: {} };
              var have = pageStatus(r.d.day).reviews || {};
              REVIEW_GAPS.forEach(function (g) {
                if (g <= r.gap && !have[String(g)]) patch.reviews[String(g)] = todayIso();
              });
              setDayStatus(r.d.day, patch)
                .then(function () {
                  toast("Day " + r.d.n + " 기록했어요");
                  setupToday();
                })
                .catch(function (err) {
                  toast("저장하지 못했어요: " + err.message, true);
                });
            })
          );
        }
        row.appendChild(btns);
        rb.appendChild(row);
        rb.appendChild(slot);
      });
      if (due.length > 3) rb.appendChild(h("div", "tc-rv-note", "나머지 " + (due.length - 3) + "개는 다음에 보여 드려요."));
      side.appendChild(rb);
    }
    var gains = gainsPanel(days);
    if (gains) side.appendChild(gains);
    if (side.children.length) card.appendChild(side);
    markRoadmap(days, cur);
    homeNext(cur);
  }

  // 홈 카드 아래 한 줄: 지금 개념과 이어지는 작은 프로젝트 단계 하나, 연구 노트
  function homeNext(cur) {
    var box = document.getElementById("home-next");
    var data = projData();
    if (!box || !data) return;
    projLoad().then(function (P) {
      box.innerHTML = "";
      var pick = null,
        lab = "작게 만들어 보기";
      var nx = P.last ? projNextStep(data, P) : null;
      if (nx) {
        pick = nx.step;
        lab = nx.label;
      } else {
        var src = cur ? cur.src : "";
        pick =
          data.steps.find(function (st) {
            return st.days.indexOf(src) >= 0 && projState(P, st.id) !== "done";
          }) ||
          data.steps.find(function (st) {
            return projState(P, st.id) !== "done";
          });
      }
      if (pick) {
        var a = h("a", "hn-item");
        a.href = projHref(pick);
        a.appendChild(h("span", "hn-k", lab));
        a.appendChild(h("span", "hn-t", pick.title));
        a.appendChild(h("span", "hn-m", pick.time + " · " + pick.needs));
        box.appendChild(a);
      }
      var n = h("a", "hn-item");
      n.href = OFFSET + "notes.html";
      n.appendChild(h("span", "hn-k", "연구 노트"));
      n.appendChild(h("span", "hn-t", "오늘 이해한 것이나 막힌 점을 한 줄 남기기"));
      box.appendChild(n);
    });
  }

  // ---------- 프로젝트 단계 진행 ----------
  // 원본: projects/projects.json → 페이지의 #project-data. 기록: 내 컴퓨터(로컬 모드)는 answers/projects.json(서버가 git에 기록),
  // 공개 사이트는 이 브라우저(localStorage)에만. 공개 배포물에는 들어가지 않는다. 저장이 실패하면 화면을 되돌리고 알린다.
  var PROJ = null;
  var PSTATE = { doing: "진행 중", done: "완료", hold: "보류" };
  function projData() {
    var el = document.getElementById("project-data");
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }
  function projLoad() {
    if (PROJ) return Promise.resolve(PROJ);
    var p;
    if (LOCAL)
      p = api("projects").catch(function () {
        return null;
      });
    else {
      var d = null;
      try {
        d = JSON.parse(recall("study-projects") || "null");
      } catch (e) {}
      p = Promise.resolve(d);
    }
    return p.then(function (d) {
      PROJ = d && d.steps ? d : { steps: {}, last: null };
      return PROJ;
    });
  }
  function projSave(next) {
    if (LOCAL)
      return api("projects", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(next),
      }).then(function (j) {
        PROJ = j.projects;
        return PROJ;
      });
    try {
      localStorage.setItem("study-projects", JSON.stringify(next));
    } catch (e) {
      return Promise.reject(new Error("이 브라우저가 저장을 막았어요(사생활 보호 창이거나 저장 공간 부족)"));
    }
    PROJ = next;
    return Promise.resolve(PROJ);
  }
  function projState(P, id) {
    return (P.steps[id] || {}).state || "";
  }
  function projHref(st) {
    return OFFSET + "projects/" + st.page + "#" + st.anchor;
  }
  function projWhere() {
    return LOCAL ? "기록은 내 컴퓨터에 저장됩니다 (answers/projects.json)." : "공개 사이트: 기록은 이 브라우저에만 저장됩니다. 내 컴퓨터 사이트의 기록과는 따로입니다.";
  }
  // 계속하기: 마지막으로 만진 단계가 끝나지 않았으면 그 단계, 끝났으면 같은 프로젝트의 다음 미완료 단계
  function projNextStep(data, P) {
    if (!P.last) return null;
    var st = data.steps.find(function (x) {
      return x.id === P.last.step;
    });
    if (!st) return null;
    var s0 = projState(P, st.id);
    if (s0 !== "done") return { step: st, label: "프로젝트 계속" + (s0 ? " · " + PSTATE[s0] : "") };
    var same = data.steps.filter(function (x) {
      return x.project === st.project;
    });
    var nx = same.slice(same.indexOf(st) + 1).find(function (x) {
      return projState(P, x.id) !== "done";
    });
    return nx ? { step: nx, label: "프로젝트 다음 단계" } : null;
  }
  function projClone(P) {
    return JSON.parse(JSON.stringify(P));
  }
  function nowStamp() {
    var d = new Date();
    return todayIso() + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
  }
  function stepBar(st, rerender) {
    var bar = h("div", "pstep");
    bar.dataset.step = st.id;
    function draw() {
      bar.innerHTML = "";
      var cur = projState(PROJ, st.id);
      var row = h("div", "pstep-row");
      row.appendChild(h("span", "pstep-k", "이 단계"));
      var grp = h("div", "pstep-btns");
      grp.setAttribute("role", "group");
      grp.setAttribute("aria-label", st.title + " 진행 상태");
      ["doing", "done", "hold"].forEach(function (k) {
        var b = button(PSTATE[k] + (cur === k ? " ✓" : ""), "pstep-b" + (cur === k ? " on" : ""), function () {
          if (cur === k && k === "done") return;
          set(cur === k ? "" : k);
        });
        b.setAttribute("aria-pressed", cur === k ? "true" : "false");
        grp.appendChild(b);
      });
      row.appendChild(grp);
      if (cur === "done")
        row.appendChild(
          button("완료 취소", "ghost lab-small", function () {
            set("");
          })
        );
      row.appendChild(h("span", "pstep-meta", st.time + " · " + st.needs));
      bar.appendChild(row);
      if (cur === "done") bar.appendChild(h("div", "pstep-note", "완료 = 실행하고 기록하고 해석함. 성능이 좋았다는 뜻은 아닙니다."));
      // 기록(선택): 날짜·설정·관찰·막힌 점·결과 파일 또는 연구 노트 링크. 긴 글은 연구 노트에.
      var logs = (PROJ.steps[st.id] || {}).log || [];
      var det = h("details", "pstep-log");
      det.appendChild(h("summary", "", logs.length ? "기록 " + logs.length + "개" : "기록 남기기 (선택)"));
      logs.forEach(function (lg, i) {
        var it = h("div", "pstep-entry");
        var head = h("div", "pstep-entry-h");
        head.appendChild(h("b", "", lg.date || ""));
        head.appendChild(
          button("지우기", "ghost lab-small", function () {
            if (!window.confirm("이 기록을 지울까요?")) return;
            var next = projClone(PROJ);
            next.steps[st.id].log.splice(i, 1);
            save(next, "기록을 지웠어요", true);
          })
        );
        it.appendChild(head);
        [["setup", "설정"], ["obs", "관찰"], ["stuck", "막힌 점"], ["link", "결과·노트"]].forEach(function (f) {
          if (!lg[f[0]]) return;
          var line = h("div", "pstep-entry-l");
          line.appendChild(h("span", "pstep-entry-k", f[1]));
          if (f[0] === "link" && /^https?:\/\//.test(lg.link)) {
            var la = h("a", "", lg.link);
            la.href = lg.link;
            la.target = "_blank";
            la.rel = "noopener";
            line.appendChild(la);
          } else line.appendChild(document.createTextNode(lg[f[0]]));
          it.appendChild(line);
        });
        det.appendChild(it);
      });
      var form = h("div", "pstep-form");
      var fields = {};
      [
        ["date", "날짜", "date"],
        ["setup", "설정 (바꾼 값, 장비, 파일)", "text"],
        ["obs", "관찰", "textarea"],
        ["stuck", "막힌 점", "text"],
        ["link", "결과 파일 위치나 연구 노트 링크", "text"],
      ].forEach(function (f) {
        var lb = h("label", "pstep-f");
        lb.appendChild(h("span", "", f[1]));
        var inp = f[2] === "textarea" ? h("textarea") : h("input");
        if (f[2] !== "textarea") inp.type = f[2];
        else inp.rows = 2;
        if (f[0] === "date") inp.value = todayIso();
        fields[f[0]] = inp;
        lb.appendChild(inp);
        form.appendChild(lb);
      });
      form.appendChild(
        button("기록 추가", "lab-small", function () {
          var item = {};
          Object.keys(fields).forEach(function (k) {
            var v = fields[k].value.trim();
            if (v) item[k] = v;
          });
          if (!item.setup && !item.obs && !item.stuck && !item.link) {
            toast("설정·관찰·막힌 점·링크 중 하나는 적어 주세요");
            return;
          }
          var next = projClone(PROJ);
          var e = (next.steps[st.id] = next.steps[st.id] || {});
          e.log = (e.log || []).concat([item]);
          next.last = { step: st.id, at: nowStamp() };
          save(next, "기록을 남겼어요", true);
        })
      );
      det.appendChild(form);
      det.appendChild(h("div", "pstep-where", projWhere() + " 긴 글은 연구 노트에 쓰고 링크만 남기세요."));
      bar.appendChild(det);
    }
    function save(next, msg, keepOpen) {
      projSave(next)
        .then(function () {
          toast(msg + (LOCAL ? "" : " (이 브라우저에만)"));
          draw();
          if (keepOpen) bar.querySelector("details.pstep-log").open = true;
          if (rerender) rerender();
        })
        .catch(function (err) {
          toast("저장하지 못했어요: " + String(err.message).replace(/\.+$/, "") + ". 화면은 저장 전 상태로 되돌렸습니다.", true);
          draw();
        });
    }
    function set(k) {
      var next = projClone(PROJ);
      var e = (next.steps[st.id] = next.steps[st.id] || {});
      if (k) {
        e.state = k;
        e.at = nowStamp();
      } else {
        delete e.state;
        delete e.at;
      }
      next.last = { step: st.id, at: nowStamp() };
      save(next, k ? st.title.split(". ")[0] + ": " + PSTATE[k] : "표시를 지웠어요");
    }
    draw();
    return bar;
  }
  function continueBox(box, data) {
    box.innerHTML = "";
    var nx = projNextStep(data, PROJ);
    if (nx) {
      var a = h("a", "pj-cont");
      a.href = projHref(nx.step);
      a.appendChild(h("span", "pj-cont-k", nx.label));
      a.appendChild(h("span", "pj-cont-t", nx.step.title + " →"));
      box.appendChild(a);
    }
    box.appendChild(h("div", "pj-where", projWhere()));
  }
  function setupProjects() {
    var data = projData();
    if (!data || document.getElementById("today-card")) return;
    projLoad().then(function () {
      var page = (location.pathname.split("/").pop() || "index.html").replace(/\.html?$/, "") + ".html";
      // 카탈로그(프로젝트 홈): 프로젝트마다 진행 수와 '계속' 단추
      function catalog() {
        document.querySelectorAll("[data-project-progress]").forEach(function (el) {
          var pid = el.dataset.projectProgress;
          var steps = data.steps.filter(function (x) {
            return x.project === pid;
          });
          var n = { doing: 0, done: 0, hold: 0 };
          steps.forEach(function (x) {
            var k = projState(PROJ, x.id);
            if (k) n[k]++;
          });
          el.textContent = n.done || n.doing || n.hold ? "단계 " + steps.length + "개 중 완료 " + n.done + " · 진행 중 " + n.doing + " · 보류 " + n.hold : "";
          var go = document.querySelector('[data-project-go="' + pid + '"]');
          var open =
            steps.find(function (x) {
              return projState(PROJ, x.id) === "doing";
            }) ||
            (n.done
              ? steps.find(function (x) {
                  return projState(PROJ, x.id) !== "done";
                })
              : null);
          if (go && open) {
            go.href = projHref(open);
            go.textContent = open.title.split(". ")[0] + " 계속 →";
          }
        });
        var cb = document.getElementById("pj-continue");
        if (cb) continueBox(cb, data);
      }
      catalog();
      // 프로젝트 상세 페이지: 단계 머리마다 상태 단추, 맨 위에 계속하기
      var mine = data.steps.filter(function (x) {
        return x.page === page;
      });
      if (!mine.length) return;
      mine.forEach(function (st) {
        var el = document.getElementById(st.anchor);
        if (!el) return;
        var head = el.matches("h1,h2,h3,h4") ? el : el.querySelector(":scope > h2, :scope > h3");
        if (!head) return;
        head.parentNode.insertBefore(stepBar(st, catalog), head.nextSibling);
      });
      var title = document.getElementById("title-block-header");
      if (title && PROJ.last) {
        var top = h("div", "pj-continue pj-continue-top");
        continueBox(top, data);
        title.parentNode.insertBefore(top, title.nextSibling);
      }
    });
  }

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
  // ---------- 왼쪽 목차: Phase 제목을 두 줄로, Day 번호와 제목을 나눠 보이기 ----------
  function setupSidebar() {
    // 위 메뉴: 지금 페이지만 강조 (Quarto가 모든 페이지에서 '홈'을 강조하는 문제)
    var here = location.pathname.replace(/index\.html$/, "");
    document.querySelectorAll(".navbar a.nav-link[href]").forEach(function (a) {
      var p = new URL(a.getAttribute("href"), location.href).pathname.replace(/index\.html$/, "");
      // 하위 폴더 탭(예: 프로젝트)은 그 안의 모든 페이지에서 강조
      var on = p === here || (/\/[^/]+\/$/.test(p) && here.indexOf(p) === 0);
      a.classList.toggle("active", on);
      if (on) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    var sb = document.getElementById("quarto-sidebar");
    if (!sb) return;
    sb.querySelectorAll(".sidebar-item-section").forEach(function (sec) {
      var head = sec.querySelector(":scope > .sidebar-item-container .menu-text");
      if (!head) return;
      var m = head.textContent.trim().match(/^Phase\s*(\d+)\s*·\s*(.+)$/);
      if (!m) return;
      var nums = [];
      sec.querySelectorAll(".sidebar-section .menu-text").forEach(function (x) {
        var k = x.textContent.match(/^Day\s*(\d+)/);
        if (k) nums.push(+k[1]);
      });
      head.textContent = "";
      var top = h("span", "sb-ph", "Phase " + m[1]);
      if (nums.length) top.appendChild(h("span", "sb-range", "Day " + nums[0] + "–" + nums[nums.length - 1]));
      head.appendChild(top);
      head.appendChild(h("span", "sb-pt", m[2]));
      head.classList.add("sb-phase");
    });
    sb.querySelectorAll("a.sidebar-link .menu-text").forEach(function (x) {
      var m = x.textContent.trim().match(/^Day\s*(\d+)\s*·\s*(.+)$/);
      if (!m) return;
      x.textContent = "";
      x.appendChild(h("span", "sb-n", "Day " + m[1]));
      x.appendChild(h("span", "sb-t", m[2]));
      x.classList.add("sb-day");
      // 두 줄에서 잘리는 긴 제목도 전체를 볼 수 있게
      x.parentNode.title = "Day " + m[1] + " · " + m[2];
    });
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
    // 휴대폰 폭에서는 머리막대에 두면 검색 아이콘이 다음 줄로 밀리므로 ☰ 메뉴 안에 둔다
    var menu = document.getElementById("navbarCollapse");
    if (menu && window.matchMedia("(max-width: 575.98px)").matches) {
      box.classList.add("in-menu");
      menu.appendChild(box);
    } else tools.appendChild(box);
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
  // 핵심 장은 id가 ch-로 시작하는 h3. 스크롤 위치는 '방문'일 뿐 읽음·이해가 아니다.
  var CUR_CH = "";
  function chTitle(x) {
    return x.textContent.replace(/\s+/g, " ").trim();
  }
  // 제목에 적힌 구간 번호(예: "0", "1-2", "학습 구간 3")와 번호를 뺀 제목. 번호가 없으면 순서 번호를 쓴다.
  // 두 쪽으로 나뉜 Day의 뒤쪽은 3구간부터 시작하므로, 순서 번호가 아니라 제목의 번호를 써야 한다.
  function chNum(x, i) {
    var m = chTitle(x).match(/^(?:학습 구간 )?(\d+(?:-\d+)?)\.\s/);
    return m ? m[1] : String(i + 1);
  }
  function chBare(x) {
    return chTitle(x).replace(/^(?:학습 구간 )?\d+(?:-\d+)?\.\s*/, "");
  }
  // Quarto는 제목의 id를 감싸는 <section>에 두고 h3에는 data-anchor-id를 남긴다
  function hid(x) {
    return x.id || x.getAttribute("data-anchor-id") || (x.parentElement && x.parentElement.tagName === "SECTION" ? x.parentElement.id : "") || "";
  }
  function setupChapters() {
    var lb = document.querySelector(".lesson-body");
    if (!lb) return;
    var all = Array.prototype.slice.call(lb.querySelectorAll("h3"));
    var core = all.filter(function (x) {
      return /^ch-/.test(hid(x));
    });
    if (core.length < 2) core = all.filter(function (x) { return hid(x); });
    if (!core.length) return;
    var extra = all.filter(function (x) {
      return hid(x) && core.indexOf(x) < 0;
    });
    var steps = document.querySelector(".day-steps[data-day]");
    var dkey = steps ? steps.dataset.day : location.pathname;
    var seenKey = "study-visited:" + dkey,
      lastKey = "study-last:" + dkey;
    var seen = {};
    try {
      seen = JSON.parse(recall(seenKey) || "{}");
      if (isSplit(dkey)) {
        var oldSeen = JSON.parse(recall("study-visited:" + srcOf(dkey)) || "{}");
        Object.keys(oldSeen).forEach(function (k) {
          if (!seen[k] && document.getElementById(k)) seen[k] = oldSeen[k];
        });
      }
    } catch (e) {}

    var map = h("nav", "chap-map");
    map.setAttribute("aria-label", "이 Day의 지도");
    map.appendChild(h("div", "cm-head", "이 Day의 지도 · 학습 구간 " + core.length + "개"));
    map.appendChild(h("div", "cm-sub", "굵은 초록 = 지금 읽는 구간 · '머묾' = 10초 이상 머문 구간(읽음·이해와는 다릅니다) · 며칠에 나눠 읽어도 됩니다"));
    var ul = h("ul", "cm-core");
    var items = core.map(function (x, i) {
      var li = h("li");
      var a = h("a");
      a.href = "#" + hid(x);
      a.appendChild(h("span", "cm-num", chNum(x, i) + "구간"));
      a.appendChild(h("span", "cm-title", chBare(x)));
      li.appendChild(a);
      ul.appendChild(li);
      return li;
    });
    map.appendChild(ul);
    if (extra.length) {
      var ex = h("div", "cm-extra");
      ex.appendChild(h("span", "", "마무리 · "));
      extra.forEach(function (x) {
        var a = h("a", "", chTitle(x));
        a.href = "#" + hid(x);
        ex.appendChild(a);
      });
      map.appendChild(ex);
    }
    var last = recall(lastKey) || (isSplit(dkey) ? recall("study-last:" + srcOf(dkey)) : null);
    if (last && !location.hash && document.getElementById(last)) {
      // 버튼은 '이어서 읽기 · 3구간'만, 구간 제목은 짧게 줄여 옆에 보조 문구로 단다
      var back = h("div", "cm-resume");
      var lastEl = document.getElementById(last);
      // 저장된 id가 구간 전체(section)를 가리키면 그 제목만 쓴다
      if (!/^H[1-6]$/.test(lastEl.tagName)) lastEl = lastEl.querySelector("h2, h3, h4") || lastEl;
      var li = core.indexOf(lastEl);
      var a2 = h("a", "sbtn primary", "이어서 읽기 · " + chNum(lastEl, li < 0 ? 0 : li) + "구간");
      a2.href = "#" + last;
      back.appendChild(a2);
      var bare = chBare(lastEl);
      back.appendChild(h("span", "cm-resume-sub", bare.length > 24 ? bare.slice(0, 23) + "…" : bare));
      map.appendChild(back);
    }
    // 구간이 바뀌는 곳마다 '지금까지 온 길' 띠: 지난 구간은 ✓와 요약 한 줄(그 구간 요점의 첫 문장), 이번 구간은 ●, 남은 구간은 ○
    function secOf(x) {
      return x.parentElement && x.parentElement.tagName === "SECTION" ? x.parentElement : null;
    }
    function gist(x) {
      var sec = secOf(x);
      var li = sec ? sec.querySelector(".keypoints li") : null;
      if (!li) return "";
      var t = li.textContent.replace(/\s+/g, " ").trim();
      var m = t.match(/^(.{12,90}?[.다])(\s|$)/);
      t = m ? m[1] : t;
      return t.length > 95 ? t.slice(0, 94) + "…" : t;
    }
    core.forEach(function (x, i) {
      if (i === 0) return;
      var sec = secOf(x) || x;
      var rp = h("div", "progress-strip");
      rp.appendChild(h("div", "ps-head", "지금까지 온 길 · 이 Day의 구간 " + core.length + "개 중 " + (i + 1) + "번째로 들어갑니다"));
      var ol = h("ol", "ps-list");
      core.forEach(function (y, j) {
        var li = h("li", j < i ? "done" : j === i ? "now" : "later");
        var head = h("div", "ps-title");
        head.appendChild(h("span", "ps-mark", j < i ? "✓" : j === i ? "●" : "○"));
        head.appendChild(h("span", "", chNum(y, j) + "구간 · " + chBare(y) + (j === i ? "  (지금부터)" : "")));
        li.appendChild(head);
        if (j < i) {
          var g = gist(y);
          if (g) li.appendChild(h("div", "ps-gist", "배운 것: " + g));
        }
        ol.appendChild(li);
      });
      rp.appendChild(ol);
      sec.parentNode.insertBefore(rp, sec);
    });
    var meta = lb.querySelector(".lesson-body .lesson-meta") || lb.querySelector(".lesson-meta");
    if (meta && meta.nextSibling) lb.insertBefore(map, meta.nextSibling);
    else lb.insertBefore(map, lb.firstChild);

    var now = h("div");
    now.id = "chap-now";
    var cn = h("div", "cn");
    var prevA = h("a", "cn-nav", "‹ 이전");
    var label = h("span", "cn-label");
    var nextA = h("a", "cn-nav", "다음 ›");
    cn.appendChild(prevA);
    cn.appendChild(label);
    cn.appendChild(nextA);
    now.appendChild(cn);
    document.body.appendChild(now);

    var cur = -2,
      timer = null,
      ticking = false;
    function compute() {
      ticking = false;
      var y = window.scrollY + 120,
        c = -1;
      core.forEach(function (x, i) {
        if (x.getBoundingClientRect().top + window.scrollY <= y) c = i;
      });
      var rect = lb.getBoundingClientRect();
      now.classList.toggle("show", rect.top < 100 && rect.bottom > 200 && c >= 0);
      if (c === cur) return; // 장이 바뀔 때만 갱신
      cur = c;
      CUR_CH = c >= 0 ? hid(core[c]) : "";
      clearTimeout(timer);
      items.forEach(function (li, i) {
        li.classList.toggle("cur", i === c);
        li.classList.toggle("seen", !!seen[hid(core[i])] && i !== c);
      });
      if (c < 0) return;
      label.textContent = chNum(core[c], c) + "구간 (" + (c + 1) + "/" + core.length + ") · " + chBare(core[c]) + (c < core.length - 1 ? "  →  다음: " + chBare(core[c + 1]).slice(0, 18) : "");
      prevA.style.visibility = c > 0 ? "" : "hidden";
      if (c > 0) prevA.href = "#" + hid(core[c - 1]);
      nextA.style.visibility = c < core.length - 1 ? "" : "hidden";
      if (c < core.length - 1) nextA.href = "#" + hid(core[c + 1]);
      var id = hid(core[c]);
      timer = setTimeout(function () {
        store(lastKey, id);
        store("study-last-any", JSON.stringify({ day: dkey, id: id, title: chTitle(core[c]), at: new Date().toISOString() }));
        if (!seen[id]) {
          seen[id] = 1;
          store(seenKey, JSON.stringify(seen));
        }
      }, 10000);
    }
    window.addEventListener(
      "scroll",
      function () {
        if (!ticking) {
          ticking = true;
          requestAnimationFrame(compute);
        }
      },
      { passive: true }
    );
    compute();
  }
  // ---------- 퀴즈 ----------
  // 응답은 문항 id로 저장한다(문항을 고치면 id도 바꾸므로 옛 답이 새 문항에 붙지 않는다).
  function norm(s) {
    return String(s)
      .toLowerCase()
      .replace(/[\s·,.;:()\[\]'"$]/g, "")
      .replace(/×/g, "x")
      .replace(/[−–—]/g, "-");
  }
  function hashStr(s) {
    var x = 0;
    for (var i = 0; i < s.length; i++) x = (x * 31 + s.charCodeAt(i)) | 0;
    return (x >>> 0).toString(36);
  }
  function setupQuiz() {
    document.querySelectorAll(".quiz[data-day]").forEach(renderQuiz);
  }
  var KIND_LABEL = { check: "잠깐 점검", end: "마무리 퀴즈", final: "종합 퀴즈", pre: "사전 테스트", post: "다시 풀기", review: "지난 학습 복습" };
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
    box.innerHTML = "";
    var items = set.items;
    var kind = set.kind || "end";
    if (kind === "end" && !box.dataset.mode && !box.closest("details")) {
      var wrapD = h("details", "practice");
      wrapD.appendChild(h("summary", "", "추가 연습 (선택) · 마무리 퀴즈 " + items.length + "문항"));
      box.parentNode.insertBefore(wrapD, box);
      wrapD.appendChild(box);
    }
    // 첫 시도 기록: 문항 id별로 한 번만 쓴다. '다시 풀기' 뒤의 답은 '정답 본 뒤 재응답'으로 따로 표시한다.
    var firstKey = "study-first:" + box.dataset.day;
    var firsts = {};
    try {
      firsts = JSON.parse(recall(firstKey) || "{}");
    } catch (e) {}
    // 사전 테스트(pre): 정답 여부와 정답만, 이유는 사후 테스트(post)에서. 사후는 같은 문항을 새로 푼다.
    var mode = box.dataset.mode || (kind === "pre" ? "pre" : "");
    if (mode === "post") kind = "post";
    box.className = "quiz quiz-" + kind;
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", (KIND_LABEL[kind] || "퀴즈") + " " + (set.title || ""));
    var key =
      mode === "pre" ? "study-pre:" + box.dataset.day : mode === "post" ? "study-post:" + box.dataset.day : "study-quiz2:" + box.dataset.day + ":" + setId;
    var saved = {};
    try {
      saved = JSON.parse(recall(key) || "{}");
    } catch (e) {}
    function qid(it, i) {
      return it.id || "i" + i + ":" + hashStr(it.q);
    }
    // 문항 내용 서명: 질문·보기·정답이 바뀌면 달라진다. 서명이 다른 옛 기록은 같은 문항으로 읽지 않는다.
    function sig(it) {
      return hashStr(JSON.stringify([it.q, it.options || null, it.a]));
    }
    function stale(it, rec) {
      if (!rec) return false;
      if (rec.v) return rec.v !== sig(it);
      // 서명 전 기록: 고른 보기 글자가 지금 보기에 없거나, 지금 정답 기준의 맞음/틀림과 어긋나면 다른 문항으로 본다
      if (it.type !== "mc" || rec.chosen == null) return false;
      var j = it.options.indexOf(rec.chosen);
      return j < 0 || (j === it.a) !== !!rec.ok;
    }
    var archived = false;
    items.forEach(function (it, i) {
      var k = qid(it, i);
      if (stale(it, saved[k])) {
        store("study-old:" + key + ":" + k, JSON.stringify(saved[k]));
        delete saved[k];
        if (firsts[k]) {
          store("study-old:" + firstKey + ":" + k, JSON.stringify(firsts[k]));
          delete firsts[k];
        }
        archived = true;
      } else if (firsts[k] && firsts[k].v && firsts[k].v !== sig(it)) {
        delete firsts[k];
        archived = true;
      }
    });
    if (archived) {
      store(key, JSON.stringify(saved));
      store(firstKey, JSON.stringify(firsts));
    }
    // 지난 학습 복습은 핵심 문항(core 표시, 없으면 앞의 4개)만 기본으로 보이고 나머지는 펼쳐서 푼다
    var coreN = items.length;
    if (kind === "review" && mode === "" && items.length > 5) {
      var flagged = items.filter(function (it) {
        return it.core;
      }).length;
      if (flagged) {
        items = items
          .filter(function (it) {
            return it.core;
          })
          .concat(
            items.filter(function (it) {
              return !it.core;
            })
          );
        coreN = flagged;
      } else coreN = 4;
    }

    var head = h("div", "quiz-head");
    var left = h("div", "quiz-left");
    left.appendChild(h("span", "quiz-kind", KIND_LABEL[kind] || "퀴즈"));
    left.appendChild(h("span", "quiz-title", set.title || ""));
    head.appendChild(left);
    var dots = h("div", "quiz-dots");
    dots.setAttribute("aria-hidden", "true");
    items.forEach(function () {
      dots.appendChild(h("span", "qdot"));
    });
    head.appendChild(dots);
    box.appendChild(head);
    var body = h("div", "quiz-body");
    box.appendChild(body);
    var banner = h("div", "quiz-banner");
    banner.setAttribute("role", "status");
    banner.style.display = "none";
    box.appendChild(banner);

    function updateScore(fresh) {
      var n = 0,
        ok = 0;
      items.forEach(function (it, i) {
        var d = dots.children[i];
        d.className = "qdot";
        var sv = saved[qid(it, i)];
        if (sv) {
          n++;
          if (sv.ok) ok++;
          d.classList.add(sv.ok ? "ok" : "no");
        }
      });
      store(key, JSON.stringify(saved));
      var coreDone = items.slice(0, coreN).every(function (it, i) {
        return saved[qid(it, i)];
      });
      if (coreDone && n > 1) {
        banner.style.display = "";
        var msg;
        if (mode === "pre") {
          msg = "사전 테스트 끝. 많이 틀려도 정상입니다. 틀린 문제가 오늘 읽을 때의 표지판이 됩니다. 이유는 학습을 마친 뒤 ⑤ 사후 테스트에서 확인합니다.";
          store("study-pre-done:" + box.dataset.day, "1");
        } else if (mode === "post") {
          var pre = {};
          try {
            pre = JSON.parse(recall("study-pre:" + box.dataset.day) || "{}");
          } catch (e) {}
          var preN = 0,
            preOk = 0,
            both = [];
          items.forEach(function (it, i) {
            var pv = pre[qid(it, i)],
              sv = saved[qid(it, i)];
            if (pv) {
              preN++;
              if (pv.ok) preOk++;
            }
            if (pv && !pv.ok && sv && !sv.ok) both.push("Q" + (i + 1));
          });
          msg =
            (preN ? "사전 " + preOk + "/" + preN + " → 다시 풀기 " + ok + "/" + n + ". 사전 테스트에서 정답을 이미 봤으므로 이 점수는 이해가 늘었다는 증거가 아니라 '다시 떠올리기' 연습입니다. 이해 점검은 구간의 잠깐 점검과 종합 퀴즈의 첫 시도로 보세요. " : "") +
            (both.length
              ? "두 번 다 틀린 문제(" + both.join(", ") + ")는 이유를 읽고, 내일 ⓪ 되살리기 때 먼저 떠올려 보세요."
              : "사전에 틀렸다가 맞힌 문제가 있다면, 왜 그런지 한 문장으로 떠올려 보세요(쓰기는 선택).");
        } else if (kind === "review") {
          msg =
            ok === n
              ? "지난 학습의 핵심을 모두 다시 확인했어요. 바로 아래 학습자료로 이어 가세요."
              : "틀린 문제에는 다시 볼 곳(새 탭)이 붙어 있습니다. 확인은 언제 해도 되고, 아래 학습자료는 그대로 이어 가도 됩니다.";
        } else {
          msg =
            ok === n
              ? "모두 맞혔어요. 이유를 자기 말로 한 문장으로 말할 수 있는지만 확인해 보세요."
              : "틀린 문제는 이유를 읽고, 해당 부분으로 돌아가 다시 풀어 보세요. 점수는 진단일 뿐입니다.";
        }
        var fN = 0,
          fOk = 0,
          re = 0;
        items.forEach(function (it, i) {
          var f = firsts[qid(it, i)];
          if (f) {
            fN++;
            if (f.ok) fOk++;
          }
          if ((saved[qid(it, i)] || {}).retry) re++;
        });
        var firstLine = mode === "" && fN ? "<div class='qb-first'>첫 시도 " + fOk + "/" + fN + (re ? " · 정답 본 뒤 다시 푼 문항 " + re + "개(이해 점검 점수에는 첫 시도만 봅니다)" : "") + "</div>" : "";
        banner.innerHTML = "<div class='qb-score'><b>" + ok + "</b> / " + n + "</div><div class='qb-msg'>" + msg + firstLine + "</div>";
        banner.className = "quiz-banner " + (mode === "pre" ? "pre" : ok === n ? "all" : ok >= n * 0.6 ? "most" : "few");
        if (mode === "pre" || mode === "post") {
          if (fresh && LOCAL) {
            var patch = {};
            patch[mode === "pre" ? "pretest" : "posttest"] = { score: ok, total: n };
            setDayStatus(box.dataset.day, patch).catch(function () {});
          }
          document.dispatchEvent(new CustomEvent("study:" + mode + "-done", { detail: { day: box.dataset.day } }));
        }
      } else banner.style.display = "none";
    }

    var more = null;
    items.forEach(function (it, i) {
      var k = qid(it, i);
      var qi = h("div", "qitem");
      var qt = h("div", "qtext");
      qt.appendChild(h("span", "qn", "Q" + (i + 1)));
      qt.appendChild(h("span", "qq", it.q));
      qi.appendChild(qt);
      var why = h("div", "qwhy");
      why.setAttribute("aria-live", "polite");
      why.style.display = "none";
      function reveal(ok, chosenText, animate, chosenIdx) {
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
        why.innerHTML = "";
        if (mode === "pre") {
          why.appendChild(h("span", "qw-badge", ok ? "정답" : "오답"));
          if (!ok) why.appendChild(h("b", "", " 정답: " + ans));
          why.appendChild(h("span", "qw-later", " · 이유는 학습 뒤 사후 테스트에서"));
          saved[k] = { ok: ok, chosen: chosenText };
          updateScore(animate);
          typeset(why);
          return;
        }
        var isRetry;
        if (saved[k]) {
          isRetry = !!saved[k].retry;
          // 이 기능 전에 푼 기록은 첫 시도로 옮겨 둔다
          if (mode === "" && !isRetry && !firsts[k]) {
            firsts[k] = { ok: saved[k].ok, at: "earlier" };
            store(firstKey, JSON.stringify(firsts));
          }
        } else if (mode === "") {
          isRetry = !!firsts[k];
          if (!firsts[k]) {
            firsts[k] = { ok: ok, at: new Date().toISOString(), v: sig(it) };
            store(firstKey, JSON.stringify(firsts));
          }
        } else isRetry = mode === "post";
        why.appendChild(h("span", "qw-badge", ok ? "정답" : "오답"));
        if (isRetry) why.appendChild(h("span", "qw-retry", mode === "post" ? "사전에 정답을 본 뒤 재응답" : "정답 본 뒤 재응답 · 첫 시도: " + (firsts[k] && firsts[k].ok ? "정답" : "오답")));
        if (!ok) why.appendChild(h("b", "", " 정답: " + ans + " "));
        why.appendChild(h("span", "", " " + (it.why || "")));
        // 고른 오답이 왜 맞지 않는지(wrongWhy[보기 번호]), 같은 자리에서 볼 짧은 개념(note)과 그림(fig)
        if (!ok && it.wrongWhy && chosenIdx != null && it.wrongWhy[chosenIdx]) why.appendChild(h("div", "qw-wrong", "고른 보기가 맞지 않는 이유: " + it.wrongWhy[chosenIdx]));
        if (!ok && it.note) why.appendChild(h("div", "qw-note", it.note));
        if (!ok && it.fig) {
          var im = h("img", "qw-fig");
          im.src = it.fig;
          im.alt = it.figAlt || "다시 볼 그림";
          im.loading = "lazy";
          why.appendChild(im);
        }
        if (!ok) {
          var row = h("div", "qw-actions");
          if (it.ref && it.ref.charAt(0) === "#" && document.querySelector(it.ref)) {
            // refLabel: 처음부터가 아니라 바로 필요한 설명·작은 예제의 이름 (예: "2×2 예제의 저장 칸 세기")
            var a = h("a", "", "↑ 다시 볼 곳: " + (it.refLabel || "해당 부분"));
            a.href = it.ref;
            row.appendChild(a);
          } else if (it.ref && it.ref.charAt(0) !== "#") {
            // 지난 학습 단위의 정확한 위치를 새 탭으로 연다(이 복습 화면은 그대로 남는다)
            var a2 = h("a", "", "↗ 다시 볼 곳(새 탭): " + (it.refLabel || "지난 학습"));
            a2.href = it.ref;
            a2.target = "_blank";
            a2.rel = "noopener";
            row.appendChild(a2);
          }
          row.appendChild(
            button("이 문제 다시 풀기", "ghost", function () {
              delete saved[k];
              store(key, JSON.stringify(saved));
              renderQuiz(box);
            })
          );
          why.appendChild(row);
        }
        saved[k] = { ok: ok, chosen: chosenText, retry: isRetry, v: sig(it) };
        updateScore(animate);
        typeset(why);
      }
      if (it.type === "ox" || it.type === "mc") {
        var opts = it.type === "ox" ? ["O  참", "X  거짓"] : it.options;
        var correct = it.type === "ox" ? (it.a ? 0 : 1) : it.a;
        var row = h("div", "qopts" + (it.type === "ox" ? " ox" : ""));
        opts.forEach(function (o, j) {
          var b = button("", "qopt", function () {
            if (qi.classList.contains("answered")) return;
            row.querySelectorAll(".qopt").forEach(function (x, m) {
              if (m === correct) x.classList.add("right");
              else if (m === j) x.classList.add("wrong");
            });
            reveal(j === correct, o, true, j);
          });
          if (it.type === "mc") b.appendChild(h("span", "qletter", LETTERS[j]));
          b.appendChild(h("span", "qlabel", o));
          row.appendChild(b);
        });
        qi.appendChild(row);
        if (saved[k]) {
          row.querySelectorAll(".qopt").forEach(function (x, m) {
            if (m === correct) x.classList.add("right");
            else if (opts[m] === saved[k].chosen) x.classList.add("wrong");
          });
          reveal(saved[k].ok, saved[k].chosen, false);
        }
      } else {
        var row2 = h("div", "qshort");
        var inp = h("input");
        inp.type = "text";
        inp.placeholder = "답을 쓰고 Enter";
        inp.autocomplete = "off";
        inp.setAttribute("aria-label", "Q" + (i + 1) + " 답");
        var check = button("확인", "primary", function () {
          if (qi.classList.contains("answered")) return;
          var v = norm(inp.value);
          if (!v) return;
          var ok = it.a.some(function (x) {
            return norm(x) === v;
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
        if (saved[k]) {
          inp.value = saved[k].chosen || "";
          inp.disabled = true;
          reveal(saved[k].ok, saved[k].chosen, false);
        }
      }
      qi.appendChild(why);
      if (i >= coreN) {
        if (!more) {
          more = h("details", "quiz-more");
          more.appendChild(h("summary", "", "더 풀어 보기 (선택) · " + (items.length - coreN) + "문항"));
          body.appendChild(more);
        }
        more.appendChild(qi);
      } else body.appendChild(qi);
    });
    if (mode === "pre" && set.challenge) {
      var ch = h("div", "quiz-challenge");
      ch.appendChild(h("div", "qc-title", "먼저 만들어 보기 (약 10분, 정답 없음)"));
      ch.appendChild(h("div", "qc-text", set.challenge));
      ch.appendChild(h("div", "qc-hint", "아래 '먼저 만들어 보기' 칸이나 공책에 해 보세요. 그림·숫자·화살표 무엇이든 좋습니다. 공부한 뒤 다시 보면 무엇이 달라졌는지 보입니다."));
      box.appendChild(ch);
    }
    var foot = h("div", "quiz-foot");
    foot.appendChild(
      h(
        "span",
        "",
        mode === "pre"
          ? "모르는 게 당연합니다. 찍어도 됩니다. 먼저 답해 본 문제는 읽을 때 더 잘 눈에 들어옵니다."
          : mode === "post"
          ? "사전 테스트와 같은 문제를 이유와 함께 다시 풉니다(선택). 결과는 이 브라우저에 남습니다."
          : kind === "check"
          ? "이해 점검: 처음 고른 답이 따로 기록됩니다. 결과는 이 브라우저에만 남습니다."
          : "결과는 이 브라우저에만 남고, 학습 완료와는 관계없어요."
      )
    );
    if (mode !== "pre")
      foot.appendChild(
        button("모두 다시 풀기", "ghost", function () {
          store(key, null);
          renderQuiz(box);
        })
      );
    box.appendChild(foot);
    updateScore(false);
    typeset(box);
  }
  function setupSrcLinks() {
    var spans = document.querySelectorAll("span.src");
    if (!spans.length) return;
    fetchJson(OFFSET + "assets/papers-index.json").then(function (idx) {
      var papers = (idx && idx.papers) || [];
      papers.sort(function (a, b) {
        return b.cite.length - a.cite.length;
      });
      spans.forEach(function (sp) {
        if (sp.closest("a")) return;
        var t = sp.textContent.replace(/\s+/g, " ").trim();
        var hit = null;
        for (var i = 0; i < papers.length; i++) {
          var c = papers[i].cite;
          var base = c.replace(/\s*\(.*\)$/, "");
          if (t.indexOf(c) === 0 || (t.indexOf(base) === 0 && !/\(/.test(c))) {
            hit = papers[i];
            break;
          }
        }
        if (!hit) {
          for (var j = 0; j < papers.length; j++) {
            var b2 = papers[j].cite.replace(/\s*\(.*\)$/, "");
            if (t.indexOf(b2) === 0) {
              hit = papers[j];
              break;
            }
          }
        }
        // 보이는 글자는 '저자, 저널, 연도'(쪽수는 뺀다), 누르면 논문 탭의 그 논문으로(없으면 참고문헌)
        var a = h("a", "src-link");
        if (hit && hit.pp) a.href = OFFSET + "papers.html#" + hit.pp;
        else a.href = OFFSET + "ledger/references.html" + (hit ? "#ref-" + hit.id : "");
        // 새 탭에서 열어 읽던 자리를 잃지 않게(2026-10-31 학습자 요청)
        a.target = "_blank";
        a.rel = "noopener";
        a.title = hit ? hit.bib : "참고문헌 페이지";
        if (hit && hit.short) sp.textContent = hit.short;
        sp.parentNode.insertBefore(a, sp);
        a.appendChild(sp);
      });
    });
  }
  // ---------- 공개 사이트에서 빠진 원문 그림 자리 ----------
  function setupPaperFigs() {
    document.querySelectorAll("figure.fig.paper img").forEach(function (img) {
      function gone() {
        var ph = h("div", "paper-missing", "그림 파일을 불러오지 못했어요 (" + img.getAttribute("src") + "). 로컬이면 assets/img/papers 폴더와 서버를, 공개 사이트면 tools/publish.json의 paper_figs 설정을 확인하세요. 캡션의 DOI 링크에서 원문을 볼 수 있습니다.");
        img.replaceWith(ph);
      }
      if (img.complete && img.naturalWidth === 0) gone();
      else img.addEventListener("error", gone);
    });
  }

  // ---------- 기초 설명으로 갔다가 읽던 곳으로 돌아오기 ----------
  function setupRecall() {
    var lb = document.querySelector(".lesson-body");
    if (!lb) return;
    var back = h("button", "", "← 읽던 곳으로 돌아가기");
    back.id = "back-btn";
    back.type = "button";
    back.style.display = "none";
    var savedY = null;
    back.addEventListener("click", function () {
      if (savedY !== null) window.scrollTo({ top: savedY, behavior: SMOOTH });
      back.style.display = "none";
      savedY = null;
    });
    document.body.appendChild(back);
    lb.addEventListener("click", function (e) {
      var a = e.target.closest("a");
      if (!a) return;
      // Quarto가 href를 절대 주소로 바꿔 두므로 hash 속성으로 읽는다
      var id = a.hash ? decodeURIComponent(a.hash.slice(1)) : "";
      if (!id || a.pathname !== location.pathname) return;
      if (!(a.classList.contains("recall") || /^b-/.test(id))) return;
      var target = document.getElementById(id);
      if (!target) return;
      savedY = window.scrollY;
      back.style.display = "";
      target.classList.add("flash");
      setTimeout(function () {
        target.classList.remove("flash");
      }, 1600);
    });
    document.querySelectorAll(".basics[id]").forEach(function (b) {
      var lab = h("div", "b-label", "기초 계단");
      b.insertBefore(lab, b.firstChild);
    });
  }

  // ---------- 단계별 보기 (계산 따라가기, 장치 동작 순서) ----------
  // ---------- ①②… 원문자는 글꼴에서 너무 작게 보여서 동그란 숫자 배지로 바꾼다 ----------
  var CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳";
  function circledIn(root) {
    if (!root) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (!/[①-⑳★]/.test(n.nodeValue)) return NodeFilter.FILTER_REJECT;
        var p = n.parentElement;
        return p && !p.closest("svg, script, style, textarea, .editable, .cnum, .star-mark") ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function (n) {
      var frag = document.createDocumentFragment();
      n.nodeValue.split(/([①-⑳★])/).forEach(function (part) {
        if (!part) return;
        var k = CIRCLED.indexOf(part);
        // 2026-10-31: 중요한 문장 앞의 ★는 형광펜과 같은 노란색 별로
        if (part === "★") {
          var st = document.createElement("span");
          st.className = "star-mark";
          st.textContent = "★";
          frag.appendChild(st);
        } else if (k >= 0) {
          var b = document.createElement("span");
          b.className = "cnum";
          b.textContent = String(k + 1);
          frag.appendChild(b);
        } else frag.appendChild(document.createTextNode(part));
      });
      n.parentNode.replaceChild(frag, n);
    });
  }
  // ---------- 출처·검증 메모는 작은 '출처' 단추로 접는다 (읽는 흐름을 끊지 않게) ----------
  function setupProv() {
    document.querySelectorAll("main span.prov").forEach(function (sp) {
      if (sp.dataset.chip || sp.closest(".quiz, details.prov")) return;
      sp.dataset.chip = "1";
      var b = h("button", "prov-chip", "출처");
      b.type = "button";
      b.title = sp.textContent.trim();
      b.setAttribute("aria-expanded", "false");
      b.addEventListener("click", function () {
        var open = sp.classList.toggle("open");
        b.setAttribute("aria-expanded", open ? "true" : "false");
      });
      sp.parentNode.insertBefore(b, sp);
    });
  }

  // ---------- 논문 탭: 주소의 #논문으로 왔으면 그 논문 칸을 화면 가운데에, 노란 테두리로 ----------
  function setupPaperTarget() {
    var id = decodeURIComponent(location.hash.slice(1));
    if (!id) return;
    if (!/^(p-|ref-)/.test(id)) return;
    // 논문 목록은 스크립트가 다시 그리고 읽던 위치 복원도 끼어들 수 있어서, 처음 1.5초 동안 몇 번 다시 맞춘다
    var userMoved = false;
    ["wheel", "touchstart", "keydown"].forEach(function (ev) {
      window.addEventListener(ev, function () { userMoved = true; }, { once: true, passive: true });
    });
    function center() {
      var el = document.getElementById(id);
      if (!el || userMoved) return;
      el.classList.add("pp-hit");
      var r = el.getBoundingClientRect();
      var want = window.scrollY + r.top - Math.max(70, (window.innerHeight - r.height) / 2);
      if (Math.abs(r.top + r.height / 2 - window.innerHeight / 2) > 40) window.scrollTo(0, Math.max(0, want));
    }
    [0, 150, 400, 800, 1500].forEach(function (t) { setTimeout(center, t); });
    window.addEventListener("load", function () { setTimeout(center, 60); });
  }

  // ---------- 다른 Day의 개념으로 가는 본문 링크는 새 탭에서 (읽던 자리를 지키려고) ----------
  function setupCrossLinks() {
    document.querySelectorAll(".lesson-body p a[href], .lesson-body li a[href], .lesson-body td a[href], .lesson-body dd a[href]").forEach(function (a) {
      if (a.target || !a.hash || a.closest(".day-steps, .progress-strip, .quiz, nav")) return;
      if (a.pathname === location.pathname || !/\/days\/d\d\d[ab]?\.html$/.test(a.pathname)) return;
      a.target = "_blank";
      a.rel = "noopener";
      a.classList.add("x-day");
    });
  }

  // ---------- 왼쪽 위 사이트 이름: 'Ions'만 색을 달리하고 작은 +를 붙인다 ----------
  function setupBrand() {
    var t = document.querySelector(".navbar-title");
    if (!t || t.querySelector(".brand-ion")) return;
    if (t.textContent.trim() !== "Why Ions Compute?") return;
    // 아주 좁은 화면(휴대폰 200% 확대 등)에서는 짧은 워드마크 'Ions⁺'만 보인다(study.css)
    t.innerHTML =
      '<span class="brand-full">Why <span class="brand-ion">Ions<sup>+</sup></span> Compute?</span>' +
      '<span class="brand-short" aria-hidden="true"><span class="brand-ion">Ions<sup>+</sup></span></span>';
  }

  function setupCircled() {
    var main = document.querySelector("main") || document.body;
    circledIn(main);
    // 퀴즈처럼 나중에 그려지는 곳도
    var pending = false;
    new MutationObserver(function () {
      if (pending) return;
      pending = true;
      setTimeout(function () {
        pending = false;
        circledIn(main);
      }, 60);
    }).observe(main, { childList: true, subtree: true });
  }

  // 2026-10-30 학습자 피드백: 버튼으로 한 장씩 넘기는 것은 집중에 도움이 안 됨 →
  // 모든 단계를 한눈에 보이는 번호 흐름(세로 타임라인)으로 보여 준다.
  function setupSteppers() {
    document.querySelectorAll(".stepper").forEach(function (st) {
      st.classList.add("flow");
    });
  }
  function setupSteppersOld() {
    document.querySelectorAll(".stepper").forEach(function (st) {
      var steps = Array.prototype.slice.call(st.querySelectorAll(":scope > .step"));
      if (steps.length < 2) return;
      var cur = 0;
      var bar = h("div", "step-bar");
      var cnt = h("span", "step-count");
      var next = button("다음 단계 →", "primary", function () {
        if (cur < steps.length - 1) {
          cur++;
          show();
          steps[cur].scrollIntoView({ block: "nearest", behavior: SMOOTH });
        }
      });
      var reset = button("처음부터", "ghost", function () {
        cur = 0;
        show();
      });
      bar.appendChild(cnt);
      bar.appendChild(next);
      bar.appendChild(reset);
      st.appendChild(bar);
      function show() {
        steps.forEach(function (s, i) {
          s.style.display = i <= cur ? "" : "none";
          s.classList.toggle("step-cur", i === cur);
        });
        cnt.textContent = "단계 " + (cur + 1) + " / " + steps.length;
        next.disabled = cur >= steps.length - 1;
        next.textContent = cur >= steps.length - 1 ? "끝" : "다음 단계 →";
      }
      show();
    });
  }

  // ---------- 백지 회상: 자료를 가리고 쓰고, 오늘의 핵심 목록과 대조한다 ----------
  function keypointsFrom(root) {
    // 장(학습 구간)별 요점 목록: [{ch, title, items:[...]}]
    var out = [];
    root.querySelectorAll(".keypoints").forEach(function (kp) {
      var sec = kp.closest("section[id^='ch-']");
      var h3 = sec && sec.querySelector("h3");
      var lis = Array.prototype.slice.call(kp.querySelectorAll("li")).map(function (li) {
        return li.textContent.replace(/\s+/g, " ").trim();
      });
      if (lis.length) out.push({ ch: sec ? sec.id : "", title: h3 ? chTitle(h3) : "", items: lis });
    });
    return out;
  }
  function renderRecallCheck(box, groups, pageHref, round) {
    var did = box.dataset.day;
    var key = "study-recallcheck:" + did + ":" + round;
    var got = {};
    try {
      got = JSON.parse(recall(key) || "{}");
    } catch (e) {}
    box.innerHTML = "";
    if (!groups.length) {
      box.appendChild(h("div", "rc-empty", "이 날의 핵심 목록이 아직 없어요."));
      return;
    }
    var total = 0;
    groups.forEach(function (g) {
      total += g.items.length;
    });
    box.appendChild(h("div", "rc-head", "내가 쓴 것과 대조하기 — 적은 항목에 체크하세요(뜻이 맞으면 표현은 달라도 됩니다)"));
    var score = h("div", "rc-score");
    box.appendChild(score);
    function update(fresh) {
      var hit = 0;
      Object.keys(got).forEach(function (k) {
        if (got[k]) hit++;
      });
      score.textContent = "적은 것 " + hit + " / " + total + (hit < total ? " · 못 적은 것이 다음에 다시 볼 곳입니다" : " · 전부 떠올렸어요");
      store(key, JSON.stringify(got));
      if (fresh && LOCAL) {
        var patch = {};
        patch[round === 2 ? "recall2" : "recall"] = { hit: hit, total: total };
        setDayStatus(did, patch).catch(function () {});
      }
    }
    groups.forEach(function (g, gi) {
      var gb = h("div", "rc-group");
      var t = h("a", "rc-ch", g.title || "핵심");
      t.href = (pageHref || "") + "#" + g.ch;
      gb.appendChild(t);
      g.items.forEach(function (txt, i) {
        var id = gi + "-" + i;
        var lab = h("label", "rc-item");
        var cb = h("input");
        cb.type = "checkbox";
        cb.checked = !!got[id];
        cb.addEventListener("change", function () {
          got[id] = cb.checked;
          lab.classList.toggle("hit", cb.checked);
          update(true);
        });
        lab.classList.toggle("hit", cb.checked);
        lab.appendChild(cb);
        lab.appendChild(h("span", "", txt));
        gb.appendChild(lab);
      });
      box.appendChild(gb);
    });
    update(false);
    typeset(box);
  }
  function setupBlankRecall() {
    document.querySelectorAll(".recall-tools[data-day]").forEach(function (tools) {
      var did = tools.dataset.day;
      var round = tools.dataset.round === "2" ? 2 : 1;
      var src = tools.dataset.src || "";
      var checkBox = document.querySelector('.recall-check[data-day="' + did + '"][data-round="' + round + '"]');
      var hideBtn = button("자료 가리고 쓰기", "primary", function () {
        var on = !document.body.classList.contains("recall-hide");
        document.body.classList.toggle("recall-hide", on);
        hideBtn.textContent = on ? "자료 다시 보이기" : "자료 가리고 쓰기";
        if (on) {
          var ed = EDITORS[did + (round === 2 ? "-recall2" : "-recall")];
          if (ed && !(ed._ta && document.body.contains(ed._ta))) ed.startEdit();
        }
      });
      var checkBtn = button("빠진 것 확인", "", function () {
        document.body.classList.remove("recall-hide");
        hideBtn.textContent = "자료 가리고 쓰기";
        if (!checkBox) return;
        checkBox.style.display = "";
        if (src) {
          checkBox.textContent = "핵심 목록을 불러오는 중…";
          fetch(src, { cache: "no-store" })
            .then(function (r) {
              return r.text();
            })
            .then(function (t) {
              var doc = new DOMParser().parseFromString(t, "text/html");
              renderRecallCheck(checkBox, keypointsFrom(doc), src, round);
            })
            .catch(function () {
              checkBox.textContent = "핵심 목록을 불러오지 못했어요.";
            });
        } else {
          var lb = document.querySelector(".lesson-body");
          renderRecallCheck(checkBox, lb ? keypointsFrom(lb) : [], "", round);
        }
        if (!tools._auto) checkBox.scrollIntoView({ behavior: SMOOTH, block: "start" });
      });
      if (round === 1) tools.appendChild(hideBtn);
      tools.appendChild(checkBtn);
      if (checkBox) {
        var done = recall("study-recallcheck:" + did + ":" + round);
        checkBox.style.display = done ? "" : "none";
        if (done) {
          tools._auto = true;
          checkBtn.click();
          tools._auto = false;
        }
      }
    });
  }

  // ---------- 조작 실습(lab): 여러 날이 다시 쓰는 작은 부품 ----------
  // <div class="lab" data-lab="이름"> 안에 정적 예제(.lab-static)를 두면, 스크립트가 성공했을 때만 실습으로 바꾼다.
  // 기록은 이 브라우저(localStorage)에만 남는다: 예측·첫 시도·힌트 사용·마지막 답을 따로 적는다.
  var LABS = {};
  function labGet(key) {
    try {
      return JSON.parse(recall("study-lab:" + key) || "null");
    } catch (e) {
      return null;
    }
  }
  function labPut(key, val) {
    store("study-lab:" + key, val == null ? null : JSON.stringify(val));
  }
  function fmtNum(v) {
    return Number(v).toLocaleString("ko-KR", { maximumFractionDigits: 3 }).replace(/^-/, "−");
  }
  // 단계형 슬라이더: 키보드 ←/→로 한 칸씩, 값은 글자로도 읽어 준다.
  function labSlider(o) {
    var wrap = h("div", "lab-ctl");
    var lab = h("label", "lab-ctl-label", o.label);
    lab.setAttribute("for", o.id);
    var inp = h("input");
    inp.type = "range";
    inp.id = o.id;
    inp.min = 0;
    inp.max = o.values.length - 1;
    inp.step = 1;
    inp.value = o.index;
    var out = h("output", "lab-ctl-value");
    out.setAttribute("for", o.id);
    function sync() {
      var v = o.values[+inp.value];
      out.textContent = o.fmt(v);
      inp.setAttribute("aria-valuetext", o.fmt(v));
    }
    inp.addEventListener("input", function () {
      sync();
      o.onInput(+inp.value);
    });
    sync();
    var row = h("div", "lab-ctl-row");
    row.appendChild(inp);
    row.appendChild(out);
    wrap.appendChild(lab);
    if (o.help) wrap.appendChild(h("div", "lab-ctl-help", o.help));
    wrap.appendChild(row);
    wrap.setIndex = function (i) {
      inp.value = i;
      sync();
    };
    return wrap;
  }
  // 선택형 점검: "모르겠음"도 답으로 받고, 첫 시도·힌트·재시도를 구분해 적는다.
  function labCheck(o) {
    var box = h("div", "lab-q");
    box.appendChild(h("div", "lab-q-text", o.question));
    var row = h("div", "lab-q-opts");
    row.setAttribute("role", "group");
    row.setAttribute("aria-label", o.question);
    var res = h("div", "lab-q-res");
    res.setAttribute("aria-live", "polite");
    var rec = labGet(o.key) || {};
    var hint = null,
      hintBtn = null;
    function show(choice) {
      row.querySelectorAll("button").forEach(function (b, j) {
        b.disabled = true;
        b.classList.toggle("right", j === o.correct);
        b.classList.toggle("wrong", j === choice && j !== o.correct && o.options[j] !== "모르겠음");
        b.setAttribute("aria-pressed", j === choice ? "true" : "false");
      });
      res.innerHTML = "";
      var unsure = o.options[choice] === "모르겠음";
      res.appendChild(h("b", "", unsure ? "괜찮아요. 모르는 데서 출발합니다. " : choice === o.correct ? "맞아요. " : "다른 답이 나왔어요. "));
      var ex = h("span");
      ex.innerHTML = choice === o.correct ? o.explain : (o.why && o.why[choice]) || o.explain;
      res.appendChild(ex);
      if (rec.first) {
        var log = "첫 시도: " + o.options[rec.first.choice] + (rec.first.hint ? " (힌트 본 뒤)" : "") + (rec.tries > 1 ? " · 정답 공개 뒤 다시 고른 횟수 " + (rec.tries - 1) : "");
        res.appendChild(h("div", "lab-q-log", log));
      }
      typeset(res);
    }
    o.options.forEach(function (label, j) {
      row.appendChild(
        button(label, "lab-opt", function () {
          rec.tries = (rec.tries || 0) + 1;
          if (!rec.first) rec.first = { choice: j, hint: !!rec.hint, at: new Date().toISOString() };
          rec.last = { choice: j, at: new Date().toISOString() };
          labPut(o.key, rec);
          show(j);
        })
      );
    });
    box.appendChild(row);
    if (o.hint) {
      hint = h("div", "lab-hint");
      hint.innerHTML = o.hint;
      hint.style.display = rec.hint ? "" : "none";
      hintBtn = button("힌트 보기", "ghost lab-small", function () {
        rec.hint = true;
        labPut(o.key, rec);
        hint.style.display = "";
        hintBtn.disabled = true;
        typeset(hint);
      });
      if (rec.hint) hintBtn.disabled = true;
      box.appendChild(hintBtn);
      box.appendChild(hint);
    }
    box.appendChild(res);
    box.appendChild(
      button("다시 풀기", "ghost lab-small", function () {
        rec.last = null;
        labPut(o.key, rec);
        row.querySelectorAll("button").forEach(function (b) {
          b.disabled = false;
          b.classList.remove("right", "wrong");
          b.removeAttribute("aria-pressed");
        });
        res.innerHTML = "";
      })
    );
    if (rec.last) show(rec.last.choice);
    return box;
  }
  function setupLabs() {
    document.querySelectorAll(".lab[data-lab]").forEach(function (el) {
      var fn = LABS[el.dataset.lab];
      if (!fn) return;
      try {
        var mount = h("div", "lab-live");
        fn(mount, el);
        el.appendChild(mount);
        el.classList.add("lab-ready");
      } catch (err) {
        el.classList.add("lab-failed");
        if (window.console) console.error("lab", el.dataset.lab, err);
      }
    });
  }

  // D2 1-1구간: 계산은 빨라도 기다릴 수 있다 (교육용 모형. 가정은 본문의 '모형의 가정'에 적어 둠)
  LABS.memwait = function (root, host) {
    var N = 1000; // 해야 할 곱해서 더하기 수
    var SPEED = [1, 2, 4, 8]; // 연산기 속도 배수: 계산 1번 = 1/배수 ns
    var BW = [0.25, 0.5, 1, 2, 4]; // 1 ns에 옮기는 숫자 수
    var REUSE = [1, 2, 4, 8]; // 가져온 숫자 하나를 쓰는 계산 수
    var AXIS = 4000; // 막대 눈금 끝(ns): 가장 느린 경우 = 1,000 ÷ 0.25
    var st = { s: 0, b: 0, r: 0 };
    var prev = null; // 직전 결과: 무엇을 바꿨을 때 무엇이 변했는지 말해 주려고
    var pred = labGet("d02-wait-predict");

    function calc() {
      var C = N / SPEED[st.s];
      var F = N / REUSE[st.r];
      var M = F / BW[st.b];
      var T = Math.max(C, M);
      return { C: C, F: F, M: M, T: T, wait: T - C };
    }

    // 1) 예측
    var pbox = h("div", "lab-q lab-predict");
    pbox.appendChild(h("div", "lab-step", "1 · 먼저 예상"));
    pbox.appendChild(h("div", "lab-q-text", "처음 설정(연산기 1×, 전송 0.25개/ns, 재사용 1)에서 연산기만 2배 빠르게 바꾸면 전체 시간은 어떻게 될까요? 고르면 기록만 하고, 답은 직접 바꿔 보면서 확인합니다."));
    var popts = ["거의 절반이 된다", "거의 그대로다", "더 길어진다", "모르겠음"];
    var prow = h("div", "lab-q-opts");
    prow.setAttribute("role", "group");
    prow.setAttribute("aria-label", "먼저 예상");
    var pmsg = h("div", "lab-q-res");
    pmsg.setAttribute("aria-live", "polite");
    popts.forEach(function (t, j) {
      prow.appendChild(
        button(t, "lab-opt", function () {
          if (!pred) pred = { choice: j, at: new Date().toISOString() };
          labPut("d02-wait-predict", pred);
          markPred();
        })
      );
    });
    function markPred() {
      prow.querySelectorAll("button").forEach(function (b, j) {
        b.disabled = !!pred;
        b.setAttribute("aria-pressed", pred && pred.choice === j ? "true" : "false");
        b.classList.toggle("chosen", !!pred && pred.choice === j);
      });
      if (pred) pmsg.textContent = "예상을 기록했어요: '" + popts[pred.choice] + "'. 첫 예상은 바뀌지 않게 남겨 둡니다. 이제 아래에서 연산기 속도만 2×로 바꿔 보세요.";
    }
    pbox.appendChild(prow);
    pbox.appendChild(pmsg);
    root.appendChild(pbox);

    // 2) 조작
    root.appendChild(h("div", "lab-step", "2 · 하나씩 바꿔 보기"));
    var ctls = h("div", "lab-ctls");
    function onCtl(key) {
      return function (i) {
        st[key] = i;
        draw(key);
      };
    }
    var sS = labSlider({ id: "lab-memwait-speed", label: "연산기 속도", help: "계산 한 번에 걸리는 시간 = 1 ÷ 배수 ns", values: SPEED, index: st.s, fmt: function (v) { return v + "× (계산 1번 " + fmtNum(1 / v) + " ns)"; }, onInput: onCtl("s") });
    var sB = labSlider({ id: "lab-memwait-bw", label: "전송 속도 (길의 폭)", help: "메모리에서 연산기로 1 ns에 옮기는 숫자 수", values: BW, index: st.b, fmt: function (v) { return fmtNum(v) + "개 / ns"; }, onInput: onCtl("b") });
    var sR = labSlider({ id: "lab-memwait-reuse", label: "재사용 횟수", help: "가져온 숫자 하나를 몇 번의 계산에 쓰나", values: REUSE, index: st.r, fmt: function (v) { return v + "번"; }, onInput: onCtl("r") });
    ctls.appendChild(sS);
    ctls.appendChild(sB);
    ctls.appendChild(sR);
    root.appendChild(ctls);
    root.appendChild(
      button("처음 설정으로", "ghost lab-small", function () {
        st = { s: 0, b: 0, r: 0 };
        sS.setIndex(0);
        sB.setIndex(0);
        sR.setIndex(0);
        prev = null;
        obs.className = "lab-observe";
        obs.innerHTML = "";
        draw(null);
      })
    );

    // 모식도와 막대 (같은 ns 눈금)
    var pic = h("div", "lab-pic");
    pic.setAttribute("aria-hidden", "true");
    var bars = h("div", "lab-bars");
    var live = h("div", "lab-live-text");
    live.setAttribute("aria-live", "polite");
    var obs = h("div", "lab-observe");
    obs.setAttribute("aria-live", "polite");
    root.appendChild(pic);
    root.appendChild(bars);
    root.appendChild(live);
    root.appendChild(obs);

    function barRow(label, value, cls, note) {
      var r = h("div", "lab-bar " + cls);
      r.appendChild(h("div", "lab-bar-label", label));
      var track = h("div", "lab-bar-track");
      var fill = h("div", "lab-bar-fill");
      fill.style.width = Math.max(0.5, (100 * value) / AXIS) + "%";
      track.appendChild(fill);
      r.appendChild(track);
      r.appendChild(h("div", "lab-bar-num", fmtNum(value) + " ns" + (note ? " · " + note : "")));
      return r;
    }
    function observe(key, v) {
      if (!key || !prev) return;
      var same = Math.abs(v.T - prev.T) < 1e-9;
      var bound = v.M > v.C ? "move" : v.M < v.C ? "compute" : "even";
      var msg;
      if (key === "s") {
        msg = same
          ? "연산기 속도를 바꿨지만 전체 시간은 " + fmtNum(v.T) + " ns 그대로입니다. 줄어든 것은 계산 시간(" + fmtNum(prev.C) + " → " + fmtNum(v.C) + " ns)뿐이고, 전체를 정하는 긴 쪽은 가져오기였습니다."
          : "연산기 속도를 바꾸자 전체 시간도 " + fmtNum(prev.T) + " → " + fmtNum(v.T) + " ns로 바뀌었습니다. 지금은 계산이 긴 쪽(또는 같은 쪽)이기 때문입니다.";
      } else {
        var what = key === "b" ? "전송 속도" : "재사용 횟수";
        msg = same
          ? what + "를 바꿔 가져오기 시간이 " + fmtNum(prev.M) + " → " + fmtNum(v.M) + " ns가 됐지만 전체는 " + fmtNum(v.T) + " ns 그대로입니다. 이미 계산이 긴 쪽이었습니다."
          : what + "를 바꾸자 가져오기 시간이 " + fmtNum(prev.M) + " → " + fmtNum(v.M) + " ns, 전체 시간이 " + fmtNum(prev.T) + " → " + fmtNum(v.T) + " ns로 바뀌었습니다.";
      }
      if (key === "s" && same && pred && prev.s === 0 && st.s === 1 && st.b === 0 && st.r === 0) msg += " (내 예상: '" + popts[pred.choice] + "')";
      var next = bound === "move" ? " 다음: 재사용이나 전송 속도를 올려 보세요." : bound === "compute" ? " 다음: 이 상태에서 연산기 속도를 바꿔 보세요." : " 계산과 가져오기가 딱 맞는 지점입니다. 여기서 어느 한쪽만 바꾸면 무엇이 달라질까요?";
      obs.innerHTML = "<b>관찰.</b> ";
      obs.appendChild(document.createTextNode(msg + next));
      obs.className = "lab-observe on";
    }
    function draw(key) {
      var v = calc();
      // 모식도: 메모리 → 길 → 연산기. 길의 굵기 = 전송 속도, 칸 하나 = 가져올 숫자 100개
      var thick = 3 + 4 * st.b;
      var tokens = Math.min(10, Math.round(v.F / 100));
      var tk = "";
      // 좁은 화면(휴대폰)에서는 글자가 읽히도록 위→아래로 세워 그린다
      if ((host || root).clientWidth < 440) {
        for (var k = 0; k < 10; k++) tk += "<rect x='" + (32 + k * 24) + "' y='38' width='18' height='18' rx='2' fill='" + (k < tokens ? "#3d6fb4" : "#e6ecf4") + "'/>";
        pic.innerHTML =
          "<svg viewBox='0 0 300 292' width='100%'>" +
          "<rect x='14' y='6' width='272' height='84' rx='8' fill='#f4f7fb' stroke='#3d6fb4'/>" +
          "<text x='150' y='28' text-anchor='middle' font-size='15' fill='#2c4f80' font-weight='700'>메모리</text>" +
          tk +
          "<text x='150' y='78' text-anchor='middle' font-size='13' fill='#333'>가져올 숫자 " + fmtNum(v.F) + "개 (한 칸 = 100개)</text>" +
          "<line x1='60' y1='96' x2='60' y2='176' stroke='#7b8794' stroke-width='" + thick + "'/>" +
          "<polygon points='49,176 71,176 60,194' fill='#7b8794'/>" +
          "<text x='86' y='130' font-size='13' fill='#333'>길: 1 ns에 " + fmtNum(BW[st.b]) + "개</text>" +
          "<text x='86' y='152' font-size='13' fill='#333'>숫자 하나 → 계산 " + REUSE[st.r] + "번</text>" +
          "<rect x='14' y='200' width='272' height='86' rx='8' fill='#eef8f3' stroke='#13936b'/>" +
          "<text x='150' y='222' text-anchor='middle' font-size='15' fill='#0f6b4f' font-weight='700'>연산기</text>" +
          "<text x='150' y='254' text-anchor='middle' font-size='26' fill='#0f6b4f'>×" + SPEED[st.s] + "</text>" +
          "<text x='150' y='276' text-anchor='middle' font-size='13' fill='#333'>계산 " + fmtNum(N) + "번</text>" +
          "</svg>";
      } else {
        for (var i = 0; i < 10; i++) tk += "<rect x='" + (22 + (i % 5) * 18) + "' y='" + (42 + Math.floor(i / 5) * 18) + "' width='13' height='13' rx='2' fill='" + (i < tokens ? "#3d6fb4" : "#e6ecf4") + "'/>";
        pic.innerHTML =
          "<svg viewBox='0 0 520 124' width='100%' height='124'>" +
          "<rect x='8' y='12' width='124' height='104' rx='8' fill='#f4f7fb' stroke='#3d6fb4'/>" +
          "<text x='70' y='32' text-anchor='middle' font-size='13' fill='#2c4f80' font-weight='700'>메모리</text>" +
          tk +
          "<text x='70' y='92' text-anchor='middle' font-size='11' fill='#555'>■ 한 칸 = 숫자 100개</text>" +
          "<text x='70' y='108' text-anchor='middle' font-size='11.5' fill='#333'>가져올 숫자 " + fmtNum(v.F) + "개</text>" +
          "<line x1='140' y1='64' x2='362' y2='64' stroke='#7b8794' stroke-width='" + thick + "'/>" +
          "<polygon points='362,53 380,64 362,75' fill='#7b8794'/>" +
          "<text x='260' y='48' text-anchor='middle' font-size='12' fill='#333'>길: 1 ns에 " + fmtNum(BW[st.b]) + "개</text>" +
          "<text x='260' y='92' text-anchor='middle' font-size='12' fill='#333'>숫자 하나 → 계산 " + REUSE[st.r] + "번에 사용</text>" +
          "<rect x='388' y='12' width='124' height='104' rx='8' fill='#eef8f3' stroke='#13936b'/>" +
          "<text x='450' y='32' text-anchor='middle' font-size='13' fill='#0f6b4f' font-weight='700'>연산기</text>" +
          "<text x='450' y='66' text-anchor='middle' font-size='22' fill='#0f6b4f'>×" + SPEED[st.s] + "</text>" +
          "<text x='450' y='92' text-anchor='middle' font-size='11.5' fill='#333'>계산 " + fmtNum(N) + "번</text>" +
          "</svg>";
      }
      bars.innerHTML = "";
      bars.appendChild(barRow("계산 시간", v.C, "is-compute", fmtNum(N) + "번 × " + fmtNum(1 / SPEED[st.s]) + " ns"));
      bars.appendChild(barRow("가져오기 시간", v.M, "is-move", fmtNum(v.F) + "개 ÷ " + fmtNum(BW[st.b]) + "개/ns"));
      var tl = h("div", "lab-bar is-total");
      tl.appendChild(h("div", "lab-bar-label", "전체 시간"));
      var track = h("div", "lab-bar-track");
      var busy = h("div", "lab-bar-fill busy");
      busy.style.width = (100 * v.C) / AXIS + "%";
      busy.title = "연산기가 계산한 시간";
      var idle = h("div", "lab-bar-fill idle");
      idle.style.width = (100 * v.wait) / AXIS + "%";
      idle.title = "연산기가 숫자를 기다린 시간";
      track.appendChild(busy);
      track.appendChild(idle);
      tl.appendChild(track);
      tl.appendChild(h("div", "lab-bar-num", fmtNum(v.T) + " ns = 계산 " + fmtNum(v.C) + " + 기다림 " + fmtNum(v.wait)));
      bars.appendChild(tl);
      var legend = h("div", "lab-axis");
      legend.innerHTML = "<span class='lg busy'></span>계산 <span class='lg idle'></span>연산기가 기다림 · 눈금 0–" + fmtNum(AXIS) + " ns, 모든 설정에서 같은 눈금";
      bars.appendChild(legend);
      var who = v.M > v.C ? "가져오기가 더 오래 걸려 연산기가 전체의 " + Math.round((100 * v.wait) / v.T) + "% 동안 기다립니다." : v.M < v.C ? "계산이 더 오래 걸립니다. 연산기는 쉬지 않고, 숫자가 먼저 도착해 기다립니다." : "계산과 가져오기가 딱 맞습니다. 아무도 기다리지 않습니다.";
      live.textContent = "전체 " + fmtNum(v.T) + " ns. " + who;
      observe(key, v);
      prev = { C: v.C, M: v.M, T: v.T, s: st.s, b: st.b, r: st.r };
    }
    markPred();
    draw(null);
    var narrowNow = (host || root).clientWidth < 440;
    window.addEventListener("resize", function () {
      var n = (host || root).clientWidth < 440;
      if (n !== narrowNow) {
        narrowNow = n;
        draw(null);
      }
    });

    // 3) 이유를 내 말로 (이 브라우저에만 저장, 채점 없음)
    root.appendChild(h("div", "lab-step", "3 · 왜 그런지 내 말로 한 줄"));
    var why = h("textarea", "lab-why");
    why.id = "lab-memwait-why";
    why.rows = 2;
    why.placeholder = "예: 연산기를 빠르게 해도 전체가 그대로였던 이유는 …";
    why.setAttribute("aria-label", "왜 그런지 내 말로 한 줄");
    why.value = recall("study-lab:d02-wait-why") || "";
    why.addEventListener("input", function () {
      store("study-lab:d02-wait-why", why.value || null);
    });
    root.appendChild(why);
    root.appendChild(h("div", "lab-note", "적은 내용은 이 브라우저에만 저장되고 채점하지 않습니다. 아래 '무슨 일이 있었나'와 비교해 보세요."));
  };

  // D2 1-1구간 끝: 새 숫자로 같은 원리 확인 (첫 시도·힌트·재시도를 따로 기록)
  LABS["memwait-check"] = function (root) {
    root.appendChild(
      labCheck({
        key: "d02-wait-new1",
        question: "다른 컴퓨터: 연산기는 계산 1번에 2 ns, 길은 1 ns에 숫자 1개, 계산 600번, 재사용 1. 이때 길을 2배로 넓히면 전체 시간은?",
        options: ["거의 절반이 된다", "그대로 1,200 ns다", "600 ns가 된다", "모르겠음"],
        correct: 1,
        hint: "계산 시간 = 600 × 2 ns, 가져오기 시간 = 600개 ÷ 1개/ns. 둘 중 긴 쪽이 전체 시간입니다.",
        explain: "계산 1,200 ns, 가져오기 600 ns라 이번에는 <b>계산이 긴 쪽</b>입니다. 길을 넓혀 가져오기가 300 ns가 되어도 전체는 계산 시간 1,200 ns 그대로입니다. 긴 쪽을 줄여야 전체가 줄어듭니다.",
        why: { 0: "길을 넓히면 가져오기만 빨라집니다. 계산 1,200 ns, 가져오기 600 ns이니 원래부터 계산이 긴 쪽이었고, 전체는 계산 시간에 묶여 있습니다.", 2: "600 ns는 넓히기 전의 가져오기 시간입니다. 전체 시간은 계산(1,200 ns)과 가져오기 중 긴 쪽입니다." },
      })
    );
    root.appendChild(
      labCheck({
        key: "d02-wait-new2",
        question: "처음 설정(연산기 1×, 전송 0.25개/ns, 계산 1,000번)에서 연산기를 놀리지 않으려면 숫자 하나를 최소 몇 번 다시 써야 할까요?",
        options: ["2번", "4번", "8번", "모르겠음"],
        correct: 1,
        hint: "재사용 r번이면 가져올 숫자는 1,000 ÷ r개, 가져오기 시간은 그것 ÷ 0.25입니다. 이것이 계산 시간 1,000 ns 이하가 되는 가장 작은 r을 찾아보세요.",
        explain: "r = 4이면 가져올 숫자 250개, 가져오기 250 ÷ 0.25 = 1,000 ns로 계산 시간과 같아집니다. 그보다 적게 쓰면 연산기가 기다리고, 더 많이 써도 전체는 계산 시간 1,000 ns보다 줄지 않습니다. 위 실습에서 재사용을 4로 놓고 확인해 보세요.",
        why: { 0: "r = 2이면 가져오기 500 ÷ 0.25 = 2,000 ns로 아직 계산(1,000 ns)보다 깁니다.", 2: "8번이면 연산기가 놀지는 않지만 최소는 아닙니다. 4번에서 이미 가져오기(1,000 ns)가 계산 시간과 같아집니다." },
      })
    );
  };

  // ---------- 실습 공용 조각: 먼저 예상, 내 말로 한 줄, 작은 그래프 ----------
  // 첫 예상은 한 번만 기록한다(나중에 바꿀 수 없음). "모르겠음"도 정상 답이다.
  function labPredict(o) {
    var rec = labGet(o.key);
    var box = h("div", "lab-q lab-predict");
    box.appendChild(h("div", "lab-step", "1 · 먼저 예상"));
    box.appendChild(h("div", "lab-q-text", o.question));
    var row = h("div", "lab-q-opts");
    row.setAttribute("role", "group");
    row.setAttribute("aria-label", "먼저 예상");
    var msg = h("div", "lab-q-res");
    msg.setAttribute("aria-live", "polite");
    function mark() {
      row.querySelectorAll("button").forEach(function (b, j) {
        b.disabled = !!rec;
        b.setAttribute("aria-pressed", rec && rec.choice === j ? "true" : "false");
        b.classList.toggle("chosen", !!rec && rec.choice === j);
      });
      if (rec) msg.textContent = "예상을 기록했어요: '" + o.options[rec.choice] + "'. 첫 예상은 바뀌지 않게 남겨 둡니다. " + (o.next || "");
    }
    o.options.forEach(function (t, j) {
      row.appendChild(
        button(t, "lab-opt", function () {
          if (!rec) rec = { choice: j, at: new Date().toISOString() };
          labPut(o.key, rec);
          mark();
        })
      );
    });
    box.appendChild(row);
    box.appendChild(msg);
    mark();
    return {
      el: box,
      label: function () {
        return rec ? o.options[rec.choice] : "";
      },
    };
  }
  function labWhy(root, key, placeholder, step) {
    root.appendChild(h("div", "lab-step", (step || "3") + " · 왜 그런지 내 말로 한 줄"));
    var ta = h("textarea", "lab-why");
    ta.rows = 2;
    ta.placeholder = placeholder;
    ta.setAttribute("aria-label", "왜 그런지 내 말로 한 줄");
    ta.value = recall("study-lab:" + key) || "";
    ta.addEventListener("input", function () {
      store("study-lab:" + key, ta.value || null);
    });
    root.appendChild(ta);
    root.appendChild(h("div", "lab-note", "이 브라우저에만 저장되고 채점하지 않습니다. 아래 설명과 비교해 보세요."));
  }
  function labObserve(root) {
    var obs = h("div", "lab-observe");
    obs.setAttribute("aria-live", "polite");
    root.appendChild(obs);
    return function (text) {
      if (!text) {
        obs.className = "lab-observe";
        obs.textContent = "";
        return;
      }
      obs.innerHTML = "<b>관찰.</b> ";
      obs.appendChild(document.createTextNode(text));
      obs.className = "lab-observe on";
    };
  }
  // 작은 선 그래프(SVG 문자열). 휴대폰에서도 글자가 읽히도록 viewBox를 작게 잡는다.
  function labPlot(o) {
    var W = 400,
      H = 210,
      L = 52,
      R = 12,
      T = 12,
      B = 44;
    function X(v) {
      return L + ((v - o.x0) / (o.x1 - o.x0)) * (W - L - R);
    }
    function Y(v) {
      var c = Math.max(o.y0, Math.min(o.y1, v));
      return T + (1 - (c - o.y0) / (o.y1 - o.y0)) * (H - T - B);
    }
    var s = "<svg class='lab-plot' viewBox='0 0 " + W + " " + H + "' width='100%' role='img' aria-label='" + escapeHtml(o.label || "그래프") + "'>";
    s += "<line x1='" + L + "' y1='" + Y(o.y0) + "' x2='" + (W - R) + "' y2='" + Y(o.y0) + "' stroke='#888'/>";
    s += "<line x1='" + L + "' y1='" + T + "' x2='" + L + "' y2='" + Y(o.y0) + "' stroke='#888'/>";
    if (o.y0 < 0 && o.y1 > 0) s += "<line x1='" + L + "' y1='" + Y(0) + "' x2='" + (W - R) + "' y2='" + Y(0) + "' stroke='#ccc' stroke-dasharray='3,3'/>";
    (o.xticks || []).forEach(function (t) {
      s += "<text x='" + X(t) + "' y='" + (Y(o.y0) + 15) + "' font-size='13' text-anchor='middle' fill='#555'>" + fmtNum(t) + "</text>";
    });
    (o.yticks || []).forEach(function (t) {
      s += "<text x='" + (L - 5) + "' y='" + (Y(t) + 4) + "' font-size='13' text-anchor='end' fill='#555'>" + fmtNum(t) + "</text>";
    });
    s += "<text x='" + (L + (W - L - R) / 2) + "' y='" + (H - 6) + "' font-size='13.5' text-anchor='middle' fill='#333'>" + escapeHtml(o.xlabel || "") + "</text>";
    s += "<text x='12' y='" + (T + (H - T - B) / 2) + "' font-size='13.5' text-anchor='middle' fill='#333' transform='rotate(-90 12 " + (T + (H - T - B) / 2) + ")'>" + escapeHtml(o.ylabel || "") + "</text>";
    (o.series || []).forEach(function (se) {
      var pts = se.pts
        .map(function (p) {
          return X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1);
        })
        .join(" ");
      if (se.line !== false) s += "<polyline points='" + pts + "' fill='none' stroke='" + se.color + "' stroke-width='" + (se.width || 2) + "'" + (se.dash ? " stroke-dasharray='" + se.dash + "'" : "") + "/>";
      if (se.dots)
        se.pts.forEach(function (p) {
          s += "<circle cx='" + X(p[0]).toFixed(1) + "' cy='" + Y(p[1]).toFixed(1) + "' r='" + (se.r || 3.5) + "' fill='" + se.color + "'/>";
        });
    });
    (o.legend || []).forEach(function (lg, i) {
      var x = W - R - 4,
        y = T + 13 + i * 17;
      s += "<text x='" + x + "' y='" + y + "' font-size='12.5' text-anchor='end' fill='" + lg[1] + "'>" + escapeHtml(lg[0]) + "</text>";
    });
    return s + "</svg>";
  }

  // D2 3구간: 2×2 행렬–벡터 곱 (교육용, 손계산 예 W = (1 3; 2 0.5), u = (2, 1)과 같은 숫자에서 시작)
  LABS.mvm = function (root) {
    var WV = [-1, 0, 0.5, 1, 2, 3];
    var UV = [-1, 0, 1, 2, 3, 4];
    var st = { w11: 3, w12: 5, w21: 4, w22: 2, u1: 3, u2: 2 };
    var prev = null;
    var pr = labPredict({
      key: "d02-mvm-predict",
      question: "위 손계산(W의 행 1 = (1, 3), 입력 u = (2, 1), 출력 y₁ = 5)에서 u₁만 2에서 4로 두 배 하면 y₁은?",
      options: ["10이 된다(두 배)", "7이 된다", "그대로 5", "모르겠음"],
      next: "아래에서 입력 u₁만 4로 바꿔 보세요.",
    });
    root.appendChild(pr.el);
    root.appendChild(h("div", "lab-step", "2 · 하나씩 바꿔 보기"));
    var grid = h("div", "lab-ctls");
    var sl = {};
    function mk(key, label, vals, help) {
      sl[key] = labSlider({ id: "lab-mvm-" + key, label: label, help: help, values: vals, index: st[key], fmt: fmtNum, onInput: function (i) { st[key] = i; draw(key); } });
      grid.appendChild(sl[key]);
    }
    mk("u1", "입력 u₁", UV, "column 1에 거는 값");
    mk("u2", "입력 u₂", UV, "column 2에 거는 값");
    mk("w11", "W[1,1]", WV, "행 1 · 자리 1");
    mk("w12", "W[1,2]", WV, "행 1 · 자리 2");
    mk("w21", "W[2,1]", WV, "행 2 · 자리 1");
    mk("w22", "W[2,2]", WV, "행 2 · 자리 2");
    root.appendChild(grid);
    root.appendChild(
      button("처음 숫자로", "ghost lab-small", function () {
        st = { w11: 3, w12: 5, w21: 4, w22: 2, u1: 3, u2: 2 };
        Object.keys(sl).forEach(function (k) {
          sl[k].setIndex(st[k]);
        });
        prev = null;
        say("");
        draw(null);
      })
    );
    var tbl = h("div", "lab-tablewrap");
    root.appendChild(tbl);
    var live = h("div", "lab-live-text");
    live.setAttribute("aria-live", "polite");
    root.appendChild(live);
    var say = labObserve(root);
    function v() {
      var w11 = WV[st.w11], w12 = WV[st.w12], w21 = WV[st.w21], w22 = WV[st.w22], u1 = UV[st.u1], u2 = UV[st.u2];
      return { w11: w11, w12: w12, w21: w21, w22: w22, u1: u1, u2: u2, p11: w11 * u1, p12: w12 * u2, p21: w21 * u1, p22: w22 * u2, y1: w11 * u1 + w12 * u2, y2: w21 * u1 + w22 * u2 };
    }
    function cell(a, b, p, hot) {
      return "<td" + (hot ? " class='hot'" : "") + ">" + fmtNum(a) + " × " + fmtNum(b) + " = <b>" + fmtNum(p) + "</b></td>";
    }
    function draw(key) {
      var x = v();
      var hot = function (k) {
        return key && (key === k || key === "u1" && (k === "p11" || k === "p21") || key === "u2" && (k === "p12" || k === "p22") || key === "w11" && k === "p11" || key === "w12" && k === "p12" || key === "w21" && k === "p21" || key === "w22" && k === "p22");
      };
      tbl.innerHTML =
        "<table class='lab-table'><thead><tr><th></th><th>자리 1 (u₁ = " + fmtNum(x.u1) + ")</th><th>자리 2 (u₂ = " + fmtNum(x.u2) + ")</th><th>더하면</th></tr></thead><tbody>" +
        "<tr><th>행 1 → y₁</th>" + cell(x.w11, x.u1, x.p11, hot("p11")) + cell(x.w12, x.u2, x.p12, hot("p12")) + "<td class='sum'>y₁ = <b>" + fmtNum(x.y1) + "</b></td></tr>" +
        "<tr><th>행 2 → y₂</th>" + cell(x.w21, x.u1, x.p21, hot("p21")) + cell(x.w22, x.u2, x.p22, hot("p22")) + "<td class='sum'>y₂ = <b>" + fmtNum(x.y2) + "</b></td></tr></tbody></table>";
      live.textContent = "출력 y = (" + fmtNum(x.y1) + ", " + fmtNum(x.y2) + "). 곱셈 4번, 덧셈 2번.";
      if (key && prev) {
        var d1 = x.y1 - prev.y1, d2 = x.y2 - prev.y2;
        var why =
          key === "u1" || key === "u2"
            ? "입력 하나를 바꾸면 그 입력이 들어가는 칸(같은 column)의 곱만 바뀝니다. 출력 변화 = 그 자리 weight × 입력 변화."
            : "weight 하나를 바꾸면 그 칸 하나의 곱만 바뀌어, 그 행의 출력 하나만 달라집니다.";
        var t = "y₁: " + fmtNum(prev.y1) + " → " + fmtNum(x.y1) + " (" + (d1 >= 0 ? "+" : "") + fmtNum(d1) + "), y₂: " + fmtNum(prev.y2) + " → " + fmtNum(x.y2) + " (" + (d2 >= 0 ? "+" : "") + fmtNum(d2) + "). " + why;
        if (key === "u1" && x.u1 === 4 && x.u2 === 1 && x.w11 === 1 && x.w12 === 3 && pr.label()) t += " (내 예상: '" + pr.label() + "')";
        say(t);
      }
      prev = x;
    }
    draw(null);
    labWhy(root, "d02-mvm-why", "예: u₁을 두 배 했는데 y₁이 두 배가 아닌 이유는 …");
  };
  LABS["mvm-check"] = function (root) {
    root.appendChild(
      labCheck({
        key: "d02-mvm-new1",
        question: "W의 행 1 = (2, −1), 입력 u = (3, 2)일 때 y₁은?",
        options: ["4", "8", "7", "모르겠음"],
        correct: 0,
        hint: "행 1과 입력을 같은 자리끼리 곱해 더합니다: 2 × 3 + (−1) × 2.",
        explain: "2 × 3 = 6, (−1) × 2 = −2, 더하면 4입니다. 음수 weight는 그 입력이 출력을 줄이는 쪽으로 작용한다는 뜻입니다.",
        why: { 1: "8은 −1을 +1로 계산한 값(6 + 2)입니다. weight의 부호까지 곱합니다.", 2: "7은 행 대신 다른 줄의 숫자를 섞어 쓴 경우에 나옵니다. 출력 1은 행 1만 씁니다." },
      })
    );
    root.appendChild(
      labCheck({
        key: "d02-mvm-new2",
        question: "W[1,2]를 0으로 바꾸면 무엇이 달라지나요?",
        options: ["u₂가 y₁에 주는 영향만 사라진다", "y₁이 0이 된다", "u₂가 모든 출력에서 사라진다", "모르겠음"],
        correct: 0,
        hint: "W[1,2]는 '행 1(출력 1)의 자리 2(입력 2)' 칸 하나입니다.",
        explain: "W[1,2]는 입력 2가 출력 1에 들어가는 세기 하나입니다. 0이 되면 그 칸의 곱만 0이 되고, y₁에는 u₁의 몫이 남고 y₂에서는 u₂의 몫(W[2,2] × u₂)이 그대로입니다. crossbar에서는 그 교차점의 device 하나가 전류를 거의 안 흘리는 것과 같습니다(3구간 뒷부분).",
        why: { 1: "y₁ = W[1,1]·u₁ + W[1,2]·u₂이므로 첫째 항은 남습니다.", 2: "u₂는 y₂에도 W[2,2]를 통해 들어갑니다. 바꾼 칸은 하나뿐입니다." },
      })
    );
  };

  // D7 0구간: 가중치 하나의 손실과 기울기 (교육용, L = (2w − 5)², 입력 2, 목표 5)
  LABS.lossgrad = function (root) {
    var WS = [-0.5, 0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5];
    var ETA = [0.01, 0.05, 0.1, 0.2, 0.25, 0.3];
    var st = { w0: 3, e: 1 };
    var path = [];
    function loss(w) {
      return Math.pow(2 * w - 5, 2);
    }
    function grad(w) {
      return 4 * (2 * w - 5);
    }
    var pr = labPredict({
      key: "d07-lossgrad-predict",
      question: "w = 1.0에서 시작합니다. 한 걸음 크기를 정하는 학습률 η를 0.05에서 0.3으로 키우면 손실은 어떻게 될까요?",
      options: ["더 빨리 0에 간다", "왔다 갔다 하며 커진다", "아무 변화 없다", "모르겠음"],
      next: "아래에서 η를 바꾸고 '한 걸음'을 여러 번 눌러 보세요.",
    });
    root.appendChild(pr.el);
    root.appendChild(h("div", "lab-step", "2 · 하나씩 바꿔 보기"));
    var grid = h("div", "lab-ctls");
    var s0 = labSlider({ id: "lab-lg-w0", label: "시작 weight w", values: WS, index: st.w0, fmt: fmtNum, onInput: function (i) { st.w0 = i; reset(); } });
    var s1 = labSlider({ id: "lab-lg-eta", label: "학습률 η (한 걸음 크기)", help: "다음 w = w − η × 기울기", values: ETA, index: st.e, fmt: fmtNum, onInput: function (i) { st.e = i; reset(); } });
    grid.appendChild(s0);
    grid.appendChild(s1);
    root.appendChild(grid);
    var btns = h("div", "btn-row");
    btns.appendChild(button("한 걸음", "primary lab-small", function () { step(1); }));
    btns.appendChild(button("다섯 걸음", "lab-small", function () { step(5); }));
    btns.appendChild(button("처음으로", "ghost lab-small", function () { st = { w0: 3, e: 1 }; s0.setIndex(3); s1.setIndex(1); reset(); say(""); }));
    root.appendChild(btns);
    var pic = h("div", "lab-pic");
    root.appendChild(pic);
    var live = h("div", "lab-live-text");
    live.setAttribute("aria-live", "polite");
    root.appendChild(live);
    var say = labObserve(root);
    function reset() {
      path = [WS[st.w0]];
      draw();
    }
    function step(n) {
      for (var i = 0; i < n; i++) {
        var w = path[path.length - 1];
        path.push(w - ETA[st.e] * grad(w));
      }
      draw();
      var first = Math.abs(path[0] - 2.5), last = Math.abs(path[path.length - 1] - 2.5);
      var f = 1 - 8 * ETA[st.e];
      var t;
      if (last > first + 1e-9) t = "걸음이 너무 커서 골짜기 바닥(w = 2.5)을 넘어 반대편 더 높은 곳으로 갑니다. 손실이 오히려 커집니다(발산). 이 식에서는 한 걸음마다 바닥까지의 거리에 (1 − 8η) = " + fmtNum(f) + "가 곱해지므로, 그 크기가 1보다 크면 발산합니다.";
      else if (Math.abs(last - first) < 1e-9 && first > 0) t = "바닥을 사이에 두고 같은 높이에서 왔다 갔다 합니다. 곱해지는 배율 (1 − 8η) = −1이라 거리가 줄지 않습니다.";
      else t = "바닥까지의 거리가 매 걸음 " + fmtNum(Math.abs(f)) + "배가 됩니다" + (f < 0 ? "(바닥을 넘었다 돌아오며)" : "") + ". 기울기가 0에 가까워질수록 걸음도 작아집니다.";
      if (ETA[st.e] === 0.3 && pr.label()) t += " (내 예상: '" + pr.label() + "')";
      say(t);
    }
    function draw() {
      var curve = [];
      for (var x = -0.5; x <= 5.5001; x += 0.1) curve.push([x, loss(x)]);
      var pts = path.map(function (w) {
        return [w, loss(w)];
      });
      var out = path.some(function (w) {
        return w < -0.5 || w > 5.5 || loss(w) > 40;
      });
      pic.innerHTML = labPlot({
        x0: -0.5, x1: 5.5, y0: 0, y1: 40, xticks: [0, 1, 2, 2.5, 3, 4, 5], yticks: [0, 10, 20, 30, 40],
        xlabel: "weight w", ylabel: "손실 L", label: "손실 L = (2w − 5)² 곡선과 지나온 w",
        series: [{ pts: curve, color: "#9aa5b1" }, { pts: pts, color: "#c0392b", width: 1.5, dots: true, dash: "4,3" }],
        legend: [["곡선: L = (2w − 5)²", "#6b7785"], ["점: 지나온 w", "#c0392b"]],
      });
      var w = path[path.length - 1];
      live.textContent =
        "지금 w = " + fmtNum(w) + ", 손실 L = " + fmtNum(loss(w)) + ", 기울기 dL/dw = " + fmtNum(grad(w)) + " → 다음 w = " + fmtNum(w) + " − " + fmtNum(ETA[st.e]) + " × (" + fmtNum(grad(w)) + ") = " + fmtNum(w - ETA[st.e] * grad(w)) +
        (out ? ". 점 일부가 그래프 밖으로 나갔습니다." : ".") + " 걸음 수 " + (path.length - 1) + ".";
    }
    reset();
    labWhy(root, "d07-lossgrad-why", "예: η가 크면 손실이 커진 이유는 …");
  };
  LABS["lossgrad-check"] = function (root) {
    root.appendChild(
      labCheck({
        key: "d07-lossgrad-new1",
        question: "같은 손실 L = (2w − 5)²에서 w = 3.5일 때 기울기는?",
        options: ["+8", "−8", "+4", "모르겠음"],
        correct: 0,
        hint: "기울기 = 2 × 오차 × 입력. 오차 = 2 × 3.5 − 5.",
        explain: "오차 = 7 − 5 = 2, 기울기 = 2 × 2 × 2 = +8입니다. 양수이므로 w를 줄여야(왼쪽으로) 손실이 줍니다.",
        why: { 1: "부호를 보세요. 오차가 +2(목표보다 큼)이면 기울기도 양수입니다.", 2: "입력 2를 곱하는 것을 빠뜨리면 4가 나옵니다." },
      })
    );
    root.appendChild(
      labCheck({
        key: "d07-lossgrad-new2",
        question: "η = 0.25로 w = 1.0에서 한 걸음 가면 w는?",
        options: ["4.0", "2.5", "1.6", "모르겠음"],
        correct: 0,
        hint: "다음 w = w − η × 기울기, w = 1.0에서 기울기는 −12.",
        explain: "1.0 − 0.25 × (−12) = 4.0입니다. 손실은 (8 − 5)² = 9로 시작점과 같습니다. 바닥(2.5)을 넘어 반대편 같은 높이로 간 것이고, 계속하면 1.0과 4.0을 오갑니다.",
        why: { 1: "바닥 2.5로 바로 가려면 걸음이 1.5여야 하는데, 0.25 × 12 = 3을 움직입니다.", 2: "1.6은 η = 0.05일 때입니다." },
      })
    );
  };

  // D9 2구간: 이완 시간 τ와 입력 간격 Δt → 다음 입력 때 남는 흔적 d = e^(−Δt/τ) (교육용 지수 감쇠 모형)
  LABS.decay = function (root) {
    var TAU = [5, 10, 20, 38, 50, 100, 200, 500];
    var DT = [1, 2, 4, 10, 20, 50, 100, 200];
    var st = { t: 3, d: 2 };
    var prev = null;
    var pr = labPredict({
      key: "d09-decay-predict",
      question: "τ = 38 ms인 device에 입력을 4 ms 간격으로 넣으면 다음 입력 때 앞 입력의 흔적이 약 90% 남습니다. 간격을 100 ms로 늘리면?",
      options: ["90% 정도 그대로", "약 7%로 줄어든다", "더 커진다", "모르겠음"],
      next: "아래에서 입력 간격만 100 ms로 바꿔 보세요.",
    });
    root.appendChild(pr.el);
    root.appendChild(h("div", "lab-step", "2 · 하나씩 바꿔 보기"));
    var grid = h("div", "lab-ctls");
    var s0 = labSlider({ id: "lab-dc-tau", label: "이완 시간 τ (device의 성질)", values: TAU, index: st.t, fmt: function (v) { return v + " ms"; }, onInput: function (i) { st.t = i; draw("t"); } });
    var s1 = labSlider({ id: "lab-dc-dt", label: "입력 간격 Δt (과제·측정의 성질)", values: DT, index: st.d, fmt: function (v) { return v + " ms"; }, onInput: function (i) { st.d = i; draw("d"); } });
    grid.appendChild(s0);
    grid.appendChild(s1);
    root.appendChild(grid);
    root.appendChild(button("처음 설정으로", "ghost lab-small", function () { st = { t: 3, d: 2 }; s0.setIndex(3); s1.setIndex(2); prev = null; say(""); draw(null); }));
    var pic = h("div", "lab-pic");
    root.appendChild(pic);
    var live = h("div", "lab-live-text");
    live.setAttribute("aria-live", "polite");
    root.appendChild(live);
    var say = labObserve(root);
    function draw(key) {
      var tau = TAU[st.t], dt = DT[st.d], d = Math.exp(-dt / tau);
      var pts = [];
      for (var k = 0; k <= 10; k++) pts.push([k, Math.pow(d, k)]);
      var cont = [];
      for (var x = 0; x <= 10.001; x += 0.1) cont.push([x, Math.exp((-x * dt) / tau)]);
      pic.innerHTML = labPlot({
        x0: 0, x1: 10, y0: 0, y1: 1, xticks: [0, 2, 4, 6, 8, 10], yticks: [0, 0.25, 0.5, 0.75, 1],
        xlabel: "몇 번째 다음 입력인가 k (시각 = k × " + dt + " ms)", ylabel: "남은 흔적", label: "입력 한 번의 흔적이 줄어드는 모양",
        series: [{ pts: cont, color: "#9aa5b1", width: 1.5 }, { pts: pts, color: "#3d6fb4", line: false, dots: true }],
        legend: [["선: device 안의 연속 감쇠 e^(−t/τ)", "#6b7785"], ["점: 입력 시점마다 남은 몫 dᵏ", "#3d6fb4"]],
      });
      var n10 = d > 0 && d < 1 ? Math.ceil(Math.log(0.1) / Math.log(d)) : Infinity;
      live.textContent =
        "d = e^(−" + dt + "/" + tau + ") = " + fmtNum(d) + " → 다음 입력 때 " + Math.round(d * 100) + "% 남음. 5번째 입력 때 " + (Math.pow(d, 5) * 100 < 0.01 ? "0.01% 미만" : fmtNum(Math.pow(d, 5) * 100) + "%") + ". 10% 아래로 줄 때까지 " + n10 + "번째 입력(약 " + fmtNum(n10 * dt) + " ms).";
      if (key && prev) {
        var t = (key === "d" ? "입력 간격" : "이완 시간") + "을 바꾸자 d가 " + fmtNum(prev) + " → " + fmtNum(d) + "가 됐습니다. 남는 몫은 τ 하나가 아니라 Δt/τ의 비로 정해집니다. 같은 device도 입력을 띄엄띄엄 넣으면 기억이 짧아 보이고, 촘촘히 넣으면 길어 보입니다.";
        if (key === "d" && dt === 100 && tau === 38 && pr.label()) t += " (내 예상: '" + pr.label() + "')";
        say(t);
      }
      prev = d;
    }
    draw(null);
    labWhy(root, "d09-decay-why", "예: 같은 device인데 간격을 늘리니 흔적이 줄어든 이유는 …");
  };
  LABS["decay-check"] = function (root) {
    root.appendChild(
      labCheck({
        key: "d09-decay-new1",
        question: "입력 간격 Δt가 이완 시간 τ와 같으면, 다음 입력 때 앞 입력의 흔적은 약 몇 %?",
        options: ["약 37%", "50%", "0%", "모르겠음"],
        correct: 0,
        hint: "d = e^(−Δt/τ)에 Δt/τ = 1을 넣습니다.",
        explain: "e^(−1) ≈ 0.37입니다. 지수 감쇠에서 τ는 '37%로 줄어드는 시간'이고, 절반이 되는 시간은 τ × ln 2 ≈ 0.69τ입니다.",
        why: { 1: "50%가 되는 시간(반감기)은 τ가 아니라 0.69τ입니다.", 2: "지수 감쇠는 유한한 시간에 정확히 0이 되지 않습니다." },
      })
    );
    root.appendChild(
      labCheck({
        key: "d09-decay-new2",
        question: "d = 0.5인 노드에서 3번 전 입력의 흔적은?",
        options: ["12.5%", "50%", "25%", "모르겠음"],
        correct: 0,
        hint: "한 번 지날 때마다 d를 곱합니다: d³.",
        explain: "0.5 × 0.5 × 0.5 = 0.125입니다. 흔적은 빼기가 아니라 곱하기로 줄어서, 몇 단계만 지나도 빠르게 작아집니다.",
        why: { 1: "50%는 바로 앞 입력(1번 전)의 흔적입니다.", 2: "25%는 2번 전입니다." },
      })
    );
  };

  // D8 2구간: 노드 두 개 reservoir의 입력 → 상태 → 출력 (본문 손계산과 같은 W, W_in, tanh)
  LABS.reservoir = function (root) {
    var W = [[0.4, 0.3], [-0.3, 0.5]],
      WIN = [1.0, -0.5];
    var SC = [0.5, 1, 2, 4];
    var GS = [0, 0.5, 1, 1.5, 2];
    var st = { s: 1, g: 2, u: [1, 0, 0, 0, 0, 0] };
    var prev = null;
    var pr = labPredict({
      key: "d08-res-predict",
      question: "처음 상태 (0, 0)에서 입력 1을 한 번만 넣고 그 뒤로는 0을 넣습니다. 3단계 뒤 상태는?",
      options: ["정확히 (0, 0)으로 돌아간다", "0은 아니지만 점점 작아진다", "계속 커진다", "모르겠음"],
      next: "아래 표에서 t = 3 줄을 보고, 'W 배율'을 0으로 바꿔 보세요.",
    });
    root.appendChild(pr.el);
    root.appendChild(h("div", "lab-step", "2 · 하나씩 바꿔 보기"));
    var seq = h("div", "lab-seq");
    seq.appendChild(h("span", "lab-ctl-label", "입력 순서 u(0)…u(5) (눌러서 0/1 바꾸기)"));
    var seqBtns = [];
    st.u.forEach(function (val, i) {
      var b = button("", "lab-opt lab-bit", function () {
        st.u[i] = st.u[i] ? 0 : 1;
        draw("u");
      });
      seqBtns.push(b);
      seq.appendChild(b);
    });
    root.appendChild(seq);
    var grid = h("div", "lab-ctls");
    var s0 = labSlider({ id: "lab-rs-s", label: "입력 세기 (입력에 곱하는 수)", values: SC, index: st.s, fmt: function (v) { return "× " + fmtNum(v); }, onInput: function (i) { st.s = i; draw("s"); } });
    var s1 = labSlider({ id: "lab-rs-g", label: "W 배율 (노드끼리 섞는 세기)", help: "0이면 지난 상태가 다음 상태에 안 들어감", values: GS, index: st.g, fmt: function (v) { return "× " + fmtNum(v); }, onInput: function (i) { st.g = i; draw("g"); } });
    grid.appendChild(s0);
    grid.appendChild(s1);
    root.appendChild(grid);
    root.appendChild(button("처음 설정으로", "ghost lab-small", function () { st = { s: 1, g: 2, u: [1, 0, 0, 0, 0, 0] }; s0.setIndex(1); s1.setIndex(2); prev = null; say(""); draw(null); }));
    var pic = h("div", "lab-pic");
    root.appendChild(pic);
    var tbl = h("div", "lab-tablewrap");
    root.appendChild(tbl);
    var say = labObserve(root);
    function run() {
      var x = [0, 0],
        rows = [];
      st.u.forEach(function (u, t) {
        var g = GS[st.g],
          s = SC[st.s];
        var z = [0, 1].map(function (i) {
          return g * (W[i][0] * x[0] + W[i][1] * x[1]) + WIN[i] * s * u;
        });
        x = z.map(Math.tanh);
        rows.push({ t: t + 1, u: u, x1: x[0], x2: x[1], y: x[0] - x[1] });
      });
      return rows;
    }
    function draw(key) {
      seqBtns.forEach(function (b, i) {
        b.textContent = "u(" + i + ") = " + st.u[i];
        b.setAttribute("aria-pressed", st.u[i] ? "true" : "false");
        b.classList.toggle("chosen", !!st.u[i]);
      });
      var rows = run();
      var r3 = function (v) {
        return (Math.round(v * 1000) / 1000).toFixed(3).replace(/^-/, "−");
      };
      pic.innerHTML = labPlot({
        x0: 0, x1: 6, y0: -1, y1: 1, xticks: [0, 1, 2, 3, 4, 5, 6], yticks: [-1, -0.5, 0, 0.5, 1],
        xlabel: "시간 단계 t", ylabel: "상태 값", label: "노드 두 개의 상태",
        series: [
          { pts: [[0, 0]].concat(rows.map(function (r) { return [r.t, r.x1]; })), color: "#13936b", dots: true },
          { pts: [[0, 0]].concat(rows.map(function (r) { return [r.t, r.x2]; })), color: "#3d6fb4", dots: true, dash: "5,3" },
        ],
        legend: [["x₁ (노드 1)", "#13936b"], ["x₂ (노드 2)", "#3d6fb4"]],
      });
      var html = "<table class='lab-table'><thead><tr><th>t</th><th>들어간 입력</th><th>x₁(t)</th><th>x₂(t)</th><th>예시 출력 y = x₁ − x₂</th></tr></thead><tbody>";
      rows.forEach(function (r) {
        html += "<tr><td>" + r.t + "</td><td>u(" + (r.t - 1) + ") = " + r.u + "</td><td>" + r3(r.x1) + "</td><td>" + r3(r.x2) + "</td><td>" + r3(r.y) + "</td></tr>";
      });
      tbl.innerHTML = html + "</tbody></table><div class='lab-note'>예시 출력의 weight (1, −1)는 설명용으로 고른 값입니다. 실제 readout weight는 4구간처럼 데이터로 학습해 정합니다.</div>";
      if (key) {
        var t;
        if (key === "g") t = GS[st.g] === 0 ? "W 배율이 0이면 지난 상태가 섞이지 않아, 입력이 0이 되는 다음 단계에 상태도 0이 됩니다. 기억이 없습니다." : "W 배율 × " + fmtNum(GS[st.g]) + ": 지난 상태가 다음 상태에 섞여 들어가는 세기가 바뀌어, 입력이 끝난 뒤 상태가 남는 길이가 달라집니다.";
        else if (key === "s") t = "입력 세기 × " + fmtNum(SC[st.s]) + ": x₁(1) = tanh(" + fmtNum(SC[st.s]) + ") = " + r3(rows[0].x1) + ". tanh는 1을 넘지 못하므로 입력을 4배로 해도 상태는 4배가 되지 않습니다(비선형, 포화).";
        else t = "입력 순서를 바꾸면 같은 시각의 상태가 달라집니다. 상태는 지금 입력만이 아니라 지난 입력들이 섞인 결과입니다.";
        if (key === "g" && GS[st.g] === 0 && pr.label()) t += " (내 예상: '" + pr.label() + "')";
        say(t);
      }
      prev = rows;
    }
    draw(null);
    labWhy(root, "d08-res-why", "예: 입력이 0인데도 상태가 0이 아닌 이유는 …");
  };
  LABS["reservoir-check"] = function (root) {
    root.appendChild(
      labCheck({
        key: "d08-res-new1",
        question: "입력 세기를 1에서 4로 올리면 x₁(1)은? (x₁(1) = tanh(1.0 × 세기))",
        options: ["0.762의 4배인 3.05", "약 0.999로 1을 넘지 못한다", "그대로 0.762", "모르겠음"],
        correct: 1,
        hint: "tanh의 출력은 언제나 −1과 1 사이입니다.",
        explain: "tanh(4) ≈ 0.999입니다. 입력이 커지면 출력이 1 근처에 눌려 붙습니다(포화). 이 비선형 덕분에 상태가 입력의 단순 배수가 아니게 되지만, 너무 세게 넣으면 입력의 차이가 지워집니다.",
        why: { 0: "선형이라면 4배가 되지만 tanh는 1을 넘지 못합니다.", 2: "입력 세기를 바꾸면 tanh 안의 값이 달라집니다." },
      })
    );
    root.appendChild(
      labCheck({
        key: "d08-res-new2",
        question: "W를 0으로 두고(노드끼리 안 섞음) 입력 1, 0, 0을 넣으면 x(2)는?",
        options: ["(0, 0)", "(0.164, −0.430)", "(0.762, −0.462)", "모르겠음"],
        correct: 0,
        hint: "x(2) = tanh(W x(1) + W_in u(1))에서 W = 0, u(1) = 0입니다.",
        explain: "W가 0이고 입력도 0이면 tanh(0) = 0이라 상태가 바로 0이 됩니다. 기억은 W(또는 device의 느린 이완)가 지난 상태를 다음으로 넘겨 줄 때만 생깁니다.",
        why: { 1: "그 값은 W가 본문의 원래 값일 때입니다.", 2: "그 값은 입력 1을 넣은 직후 x(1)입니다." },
      })
    );
  };

  // ---------- 그림 클릭 확대 (원문 그림의 작은 글씨를 읽기 위해) ----------
  // ---------- 그림 크기: 그림 속 글자가 본문 글자의 약 0.9배로 보이게(tools/fig_sizes.py가 잰 값) ----------
  // Day 9: 센서 노드 전력 비교 도구 (교육용 모형. 가정은 본문의 '모형의 가정'에 적어 둠)
  // 기본값은 본문 계산과 같다: A 621, B 약 24, C 약 4, D 약 7 µW. 가정을 바꾸면 MCU 쪽(B·D)이 더 작아질 수도 있다.
  LABS.budget = function (root) {
    var FS = [100, 250, 500, 1000, 2000]; // 샘플링률 S/s
    var BITS = [8, 10, 12, 16];
    var EV = [0.1, 0.5, 1, 2, 5, 10]; // 사건 수 /s
    var RADIO = [16, 50, 400]; // 무선 nJ/bit
    var ALWAYS = [0.1, 0.3, 1, 3, 10, 30]; // 늘 켜진 전처리(device + 읽기 회로) µW
    var NN = [0.3, 1, 3, 10]; // 작은 신경망 판정 한 번 µJ (1초에 한 번 판정)
    var DEF = { fs: 3, bits: 2, ev: 3, radio: 1, always: 2, nn: 2 };
    var st = JSON.parse(JSON.stringify(DEF));
    var ADC = 1, MCU = 20, MSG = 16, SLEEP = 1.2; // nJ/변환, nJ/샘플, bit/사건, µW

    function calc() {
      var fs = FS[st.fs], b = BITS[st.bits], ev = EV[st.ev], e = RADIO[st.radio];
      var uw = function (nJps) {
        return nJps / 1000;
      };
      var send = uw(ev * MSG * e);
      return [
        { k: "A", name: "Raw signal 전부 송신", bps: fs * b, parts: [["ADC", uw(fs * ADC)], ["MCU", uw(fs * MCU)], ["무선", uw(fs * b * e)]] },
        { k: "B", name: "MCU가 매 샘플 처리, 사건만 송신", bps: ev * MSG, parts: [["ADC", uw(fs * ADC)], ["MCU", uw(fs * MCU)], ["무선", send], ["MCU 잠듦", SLEEP]] },
        { k: "C", name: "Near-sensor device가 지켜보다 사건 때만 깨움", bps: ev * MSG, parts: [["늘 켜진 전처리", ALWAYS[st.always]], ["ADC", uw(ev * ADC)], ["MCU", uw(ev * MCU)], ["무선", send], ["MCU 잠듦", SLEEP]] },
        { k: "D", name: "MCU + 작은 신경망 (1초에 한 번 판정)", bps: ev * MSG, parts: [["ADC", uw(fs * ADC)], ["신경망", NN[st.nn]], ["무선", send], ["MCU 잠듦", SLEEP]] },
      ].map(function (r) {
        r.total = r.parts.reduce(function (a, p) {
          return a + p[1];
        }, 0);
        return r;
      });
    }
    function fmtUw(v) {
      return v >= 100 ? Math.round(v).toLocaleString("ko-KR") : v >= 10 ? v.toFixed(1) : v >= 1 ? v.toFixed(2) : v.toFixed(3);
    }

    root.appendChild(
      labCheck({
        key: "d05-budget-predict",
        question: "먼저 예상: 다른 값은 그대로 두고 '늘 켜진 전처리' 전력만 키우면, 약 몇 µW부터 D(MCU + 작은 신경망)가 C보다 작아질까요?",
        options: ["약 1 µW", "약 4 µW", "약 30 µW", "모르겠음"],
        correct: 1,
        explain: "C의 나머지(ADC·MCU 사건 때만 + 무선 1.6 + 잠듦 1.2)가 약 2.8 µW, D가 약 6.8 µW라서, 전처리가 약 4 µW를 넘으면 D가 작아집니다. 아래에서 직접 바꿔 확인해 보세요.",
      })
    );

    var ctl = h("div", "lab-ctls");
    var sliders = {};
    function add(key, label, values, fmt, help) {
      var s = labSlider({
        id: "bud-" + key,
        label: label,
        values: values,
        index: st[key],
        fmt: fmt,
        help: help,
        onInput: function (i) {
          st[key] = i;
          draw();
        },
      });
      sliders[key] = s;
      ctl.appendChild(s);
    }
    add("fs", "샘플링률", FS, function (v) {
      return v.toLocaleString("ko-KR") + " S/s";
    });
    add("bits", "샘플당 bit", BITS, function (v) {
      return v + " bit";
    });
    add("ev", "사건 수", EV, function (v) {
      return v + "번/s";
    }, "이상 박동처럼 보낼 사건이 1초에 몇 번 생기나");
    add("radio", "무선 1 bit의 에너지", RADIO, function (v) {
      return v + " nJ/bit";
    }, "16 = 칩이 전파를 내는 순간만, 50 = 본문 가정, 400 = 준비·연결 유지까지 넣은 실측");
    add("always", "늘 켜진 전처리 (device + 읽기 회로)", ALWAYS, function (v) {
      return v + " µW";
    }, "C에만 들어감. 아직 잰 값이 없는 가정");
    add("nn", "신경망 판정 한 번", NN, function (v) {
      return v + " µJ";
    }, "D에만 들어감. 1초에 한 번 판정");
    root.appendChild(ctl);

    var out = h("div", "bud-out");
    out.setAttribute("aria-live", "polite");
    root.appendChild(out);
    root.appendChild(
      button("처음 값으로", "ghost lab-small", function () {
        st = JSON.parse(JSON.stringify(DEF));
        Object.keys(sliders).forEach(function (k) {
          sliders[k].setIndex(st[k]);
        });
        draw();
      })
    );

    function draw() {
      var rows = calc();
      var max = Math.max.apply(null, rows.map(function (r) {
        return r.total;
      }));
      out.innerHTML = "";
      var tb = h("table", "bud-table");
      var hd = h("tr");
      ["설계", "보내는 데이터", "평균 전력", "구성 (큰 순서)"].forEach(function (t) {
        hd.appendChild(h("th", "", t));
      });
      var thead = h("thead");
      thead.appendChild(hd);
      tb.appendChild(thead);
      var body = h("tbody");
      rows.forEach(function (r) {
        var tr = h("tr");
        var c0 = h("td");
        c0.appendChild(h("b", "", r.k + " "));
        c0.appendChild(document.createTextNode(r.name));
        tr.appendChild(c0);
        tr.appendChild(h("td", "bud-num", r.bps.toLocaleString("ko-KR", { maximumFractionDigits: 1 }) + " bit/s"));
        var c2 = h("td", "bud-num");
        c2.appendChild(h("b", "", fmtUw(r.total) + " µW"));
        var bar = h("span", "bud-bar");
        // 로그 눈금 막대: 0.1 µW → 0, 최댓값 → 100%
        var lo = Math.log10(0.1), hi = Math.log10(Math.max(max, 1));
        bar.style.width = Math.max(4, (100 * (Math.log10(r.total) - lo)) / (hi - lo)) + "%";
        bar.setAttribute("aria-hidden", "true");
        c2.appendChild(bar);
        tr.appendChild(c2);
        var parts = r.parts.slice().sort(function (a, b) {
          return b[1] - a[1];
        });
        tr.appendChild(
          h(
            "td",
            "bud-parts",
            parts
              .map(function (p) {
                return p[0] + " " + Math.round((100 * p[1]) / r.total) + "%";
              })
              .join(" · ")
          )
        );
        body.appendChild(tr);
      });
      tb.appendChild(body);
      out.appendChild(tb);
      var C = rows[2].total, D = rows[3].total, B = rows[1].total;
      var best = rows.slice().sort(function (a, b) {
        return a.total - b.total;
      })[0];
      var msg = "이 가정에서 가장 작은 것은 " + best.k + "(" + fmtUw(best.total) + " µW)입니다. ";
      msg += C < D ? "C가 D보다 " + (D / C).toFixed(1) + "배 작습니다." : "D(MCU + 작은 신경망)가 C보다 " + (C / D).toFixed(1) + "배 작습니다.";
      if (B < C) msg += " MCU가 매 샘플을 처리하는 B도 C보다 작습니다.";
      out.appendChild(h("p", "bud-msg", msg));
      out.appendChild(h("p", "bud-note", "교육용 계산입니다. 네 설계가 같은 일을 같은 정확도로 한다고 가정했고, 센서·증폭기 전력은 넣지 않았습니다. 막대는 로그 눈금입니다."));
    }
    draw();
  };

  function setupFigSizes() {
    var imgs = document.querySelectorAll("figure.fig img");
    if (!imgs.length) return;
    fetchJson(OFFSET + "assets/fig-sizes.json").then(function (sizes) {
      if (!sizes) return;
      imgs.forEach(function (img) {
        if (img.closest("figure.photo")) return;
        var src = img.getAttribute("src") || "";
        var k = src.indexOf("assets/img/");
        if (k < 0) return;
        var r = sizes[src.slice(k + 11).split("?")[0]];
        if (!r || !r.em) return;
        // em이라 글자 크기 단추(가−/가+)를 눌러도 그림이 같이 따라간다. 원본보다 크게 늘이지는 않는다.
        img.style.maxWidth = r.natural ? "min(" + r.em + "em, " + r.natural + "px, 100%)" : "min(" + r.em + "em, 100%)";
        img.classList.add("sized");
      });
    });
  }

  function setupFigZoom() {
    var imgs = document.querySelectorAll("figure.fig img");
    if (!imgs.length) return;
    var ov = h("div");
    ov.id = "fig-zoom";
    ov.setAttribute("role", "dialog");
    ov.setAttribute("aria-label", "그림 크게 보기");
    ov.setAttribute("aria-modal", "true");
    // 키보드 사용자를 위해 닫기 버튼에 초점을 두고, 열려 있는 동안 Tab이 밖으로 나가지 않게 한다
    var closeBtn = button("닫기 ✕", "fz-close", function (e) {
      e.stopPropagation();
      close();
    });
    ov.appendChild(closeBtn);
    var inner = h("div", "fz-inner");
    var big = h("img");
    var cap = h("div", "fz-cap");
    inner.appendChild(big);
    inner.appendChild(cap);
    ov.appendChild(inner);
    ov.appendChild(h("div", "fz-hint", "클릭, Esc 또는 닫기 버튼으로 닫기 · 그림이 크면 스크롤"));
    document.body.appendChild(ov);
    var last = null;
    function close() {
      ov.classList.remove("show");
      document.body.classList.remove("fz-open");
      if (last) last.focus();
    }
    ov.addEventListener("click", function (e) {
      if (e.target.closest("a")) return;
      close();
    });
    document.addEventListener("keydown", function (e) {
      if (!ov.classList.contains("show")) return;
      if (e.key === "Escape") close();
      else if (e.key === "Tab") {
        e.preventDefault();
        closeBtn.focus();
      }
    });
    imgs.forEach(function (img) {
      img.classList.add("zoomable");
      img.tabIndex = 0;
      img.setAttribute("role", "button");
      img.setAttribute("aria-label", (img.alt || "그림") + " — 크게 보기");
      function open() {
        if (img.naturalWidth === 0) return;
        last = img;
        big.src = img.currentSrc || img.src;
        big.alt = img.alt;
        var fc = img.closest("figure") && img.closest("figure").querySelector("figcaption");
        cap.innerHTML = fc ? fc.innerHTML : "";
        ov.classList.add("show");
        document.body.classList.add("fz-open");
        ov.scrollTop = 0;
        closeBtn.focus();
      }
      img.addEventListener("click", open);
      img.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      });
    });
  }

  // ---------- 검색 ----------
  // Quarto 기본 검색창 대신: 같은 search.json을 한 번 읽어 두고, 한글 조합 중에도 글자마다 바로 다시 찾는다.
  // 순서는 제목 > 소제목 > 본문 등장 횟수, 같은 페이지의 결과는 한 묶음으로. 결과 목록은 보통 스크롤 상자라 휠이 그대로 먹는다.
  function setupSearch() {
    var qs = document.getElementById("quarto-search");
    if (!qs) return;
    var openBtn = h("button", "ss-open");
    openBtn.type = "button";
    openBtn.title = "검색 (/)";
    openBtn.setAttribute("aria-label", "검색");
    openBtn.innerHTML =
      '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>';
    qs.parentNode.insertBefore(openBtn, qs);
    qs.style.display = "none";
    var index = null,
      ov = null,
      input,
      list,
      sel = -1,
      items = [];
    function load() {
      if (index) return Promise.resolve(index);
      return fetch(OFFSET + "search.json")
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          index = d
            .filter(function (x) {
              return x.href && !/^index\.html/.test(x.href);
            })
            .map(function (x) {
              var text = (x.text || "").replace(/\s+/g, " ").trim();
              return { href: x.href, page: x.href.split("#")[0], title: x.title || "", section: x.section || "", text: text, lt: (x.title || "").toLowerCase(), ls: (x.section || "").toLowerCase(), lx: text.toLowerCase() };
            });
          return index;
        });
    }
    function count(hay, t) {
      var n = 0,
        i = hay.indexOf(t);
      while (i >= 0 && n < 8) {
        n++;
        i = hay.indexOf(t, i + t.length);
      }
      return n;
    }
    function mark(s, terms) {
      var out = escapeHtml(s);
      terms.forEach(function (t) {
        var re = new RegExp("(" + escapeHtml(t).replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi");
        out = out.replace(re, "<mark>$1</mark>");
      });
      return out;
    }
    function snippet(e, terms) {
      var i = e.lx.indexOf(terms[0]);
      if (i < 0) return e.text.slice(0, 90);
      var a = Math.max(0, i - 30);
      return (a > 0 ? "…" : "") + e.text.slice(a, a + 110) + (a + 110 < e.text.length ? "…" : "");
    }
    function run() {
      var q = input.value.trim().toLowerCase();
      list.innerHTML = "";
      items = [];
      sel = -1;
      if (!q) {
        list.appendChild(h("div", "ss-empty", "찾을 낱말을 입력하세요. 예: 이온, reservoir, EDL"));
        return;
      }
      if (!index) {
        list.appendChild(h("div", "ss-empty", "검색 목록을 불러오는 중…"));
        return;
      }
      var terms = q.split(/\s+/).filter(Boolean);
      var pages = {},
        order = [];
      index.forEach(function (e) {
        var sc = 0;
        for (var k = 0; k < terms.length; k++) {
          var t = terms[k],
            s = (e.lt.indexOf(t) >= 0 ? 12 : 0) + (e.ls.indexOf(t) >= 0 ? 6 : 0) + count(e.lx, t);
          if (!s) return;
          sc += s;
        }
        var p = pages[e.page];
        if (!p) {
          p = pages[e.page] = { title: e.title, best: 0, total: 0, hits: [] };
          order.push(p);
        }
        p.best = Math.max(p.best, sc);
        p.total += sc;
        p.hits.push({ e: e, sc: sc });
      });
      order.sort(function (a, b) {
        return b.best + b.total * 0.2 - (a.best + a.total * 0.2);
      });
      if (!order.length) {
        list.appendChild(h("div", "ss-empty", "‘" + input.value.trim() + "’이(가) 들어간 곳이 없어요."));
        return;
      }
      list.appendChild(h("div", "ss-count", order.length + "개 페이지"));
      order.slice(0, 30).forEach(function (p) {
        var g = h("div", "ss-group");
        g.appendChild(h("div", "ss-page", p.title));
        p.hits
          .sort(function (a, b) {
            return b.sc - a.sc;
          })
          .slice(0, 3)
          .forEach(function (x) {
            var a = h("a", "ss-item");
            a.href = OFFSET + x.e.href;
            var sec = x.e.section && x.e.section !== p.title ? x.e.section : "";
            a.innerHTML = (sec ? '<span class="ss-sec">' + mark(sec, terms) + "</span>" : "") + '<span class="ss-snip">' + mark(snippet(x.e, terms), terms) + "</span>";
            a.addEventListener("mousemove", function () {
              pick(items.indexOf(a), true);
            });
            items.push(a);
            g.appendChild(a);
          });
        list.appendChild(g);
      });
      pick(0, true);
    }
    function pick(i, noScroll) {
      if (!items.length) return;
      if (sel >= 0 && items[sel]) items[sel].classList.remove("is-sel");
      sel = Math.max(0, Math.min(items.length - 1, i));
      items[sel].classList.add("is-sel");
      if (!noScroll) items[sel].scrollIntoView({ block: "nearest" });
    }
    function close() {
      if (!ov) return;
      ov.classList.remove("is-open");
      document.documentElement.classList.remove("ss-lock");
    }
    function open() {
      if (!ov) {
        ov = h("div", "ss-overlay");
        var box = h("div", "ss-box");
        box.setAttribute("role", "dialog");
        box.setAttribute("aria-label", "검색");
        var bar = h("div", "ss-bar");
        bar.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>';
        input = h("input", "ss-input");
        input.type = "search";
        input.placeholder = "용어·개념·Day 제목 검색";
        input.setAttribute("autocomplete", "off");
        bar.appendChild(input);
        bar.appendChild(button("닫기", "ss-close", close));
        list = h("div", "ss-list");
        box.appendChild(bar);
        box.appendChild(list);
        ov.appendChild(box);
        document.body.appendChild(ov);
        ov.addEventListener("mousedown", function (e) {
          if (e.target === ov) close();
        });
        input.addEventListener("input", run);
        input.addEventListener("keydown", function (e) {
          if (e.isComposing) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            pick(sel + 1);
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            pick(sel - 1);
          } else if (e.key === "Enter" && items[sel]) {
            e.preventDefault();
            location.href = items[sel].href;
            close();
          } else if (e.key === "Escape") close();
        });
      }
      ov.classList.add("is-open");
      document.documentElement.classList.add("ss-lock");
      input.focus();
      input.select();
      run();
      load().then(run, function () {
        list.innerHTML = "";
        list.appendChild(h("div", "ss-empty", "검색 목록을 불러오지 못했어요."));
      });
    }
    openBtn.addEventListener("click", open);
    document.addEventListener(
      "keydown",
      function (e) {
        var tag = (e.target.tagName || "").toLowerCase();
        if (tag === "input" || tag === "textarea" || e.target.isContentEditable) return;
        if (e.key === "/" || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k")) {
          e.preventDefault();
          e.stopPropagation();
          open();
        }
      },
      true
    );
  }

  // ---------- 논문 탭: 찾기·종류·주제 거르기와 정렬 ----------
  function setupPapers() {
    var listEl = document.querySelector(".paper-list");
    if (!listEl) return;
    var cards = Array.prototype.slice.call(listEl.querySelectorAll(".paper"));
    var q = document.querySelector(".pp-q"),
      sortSel = document.querySelector(".pp-sort select"),
      nEl = document.querySelector(".pp-n"),
      empty = document.querySelector(".pp-empty"),
      labSel = document.querySelector(".pp-lab select");
    var f = { kind: "", topic: "", lab: "" };
    // 카드의 교신·마지막 저자 이름을 누르면 그 연구실 논문만(목록에 없는 1편짜리 연구실도 임시 항목으로 넣는다)
    function setLab(v, label) {
      f.lab = v;
      if (labSel) {
        if (v && !labSel.querySelector('option[value="' + v.replace(/"/g, "") + '"]')) {
          var o = document.createElement("option");
          o.value = v;
          o.textContent = label || v;
          labSel.appendChild(o);
        }
        labSel.value = v;
      }
      apply();
    }
    if (labSel) labSel.addEventListener("change", function () { setLab(labSel.value); });
    listEl.addEventListener("click", function (e) {
      var b = e.target.closest(".pp-au");
      if (!b) return;
      setLab(f.lab === b.dataset.lab ? "" : b.dataset.lab, b.textContent.replace("✉", ""));
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    var saved = recall("study-papers-sort");
    if (saved && sortSel) sortSel.value = saved;
    document.querySelectorAll(".pp-chips").forEach(function (g) {
      g.addEventListener("click", function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        g.querySelectorAll("button").forEach(function (x) {
          x.classList.toggle("on", x === b);
        });
        f[g.dataset.filter] = b.dataset.v;
        apply();
      });
    });
    function apply() {
      var terms = (q.value || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
      var key = sortSel ? sortSel.value : "score";
      store("study-papers-sort", key);
      cards.sort(function (a, b) {
        var A = a.dataset, B = b.dataset;
        if (key === "year") return B.year - A.year || B.score - A.score;
        if (key === "easy") return A.diff - B.diff || B.score - A.score || B.year - A.year;
        return B.score - A.score || B.year - A.year;
      });
      var shown = 0;
      cards.forEach(function (c) {
        var k = c.dataset.kind;
        var ok =
          (!f.kind || (f.kind === "other" ? k !== "review" && k !== "article" : k === f.kind)) &&
          (!f.topic || c.dataset.topic === f.topic) &&
          (!f.lab || c.dataset.lab.split("|").indexOf(f.lab) >= 0) &&
          terms.every(function (t) {
            return c.dataset.hay.indexOf(t) >= 0;
          });
        c.hidden = !ok;
        if (ok) shown++;
        listEl.appendChild(c);
      });
      nEl.textContent = shown;
      empty.hidden = shown > 0;
    }
    q.addEventListener("input", apply);
    if (sortSel) sortSel.addEventListener("change", apply);
    apply();
  }

  // ---------- 떠다니는 이온(홈 배경 장식만) ----------
  // 학습 단위 본문에는 넣지 않는다(읽기 방해). 카드 뒤 빈 곳에서만 보이도록 맨 뒤에 깔고, 움직임 줄이기 설정이면 멈춘 점으로.
  function setupDrift() {
    var b = document.body.classList;
    if (!b.contains("home")) return;
    var cv = document.createElement("canvas");
    cv.className = "ion-drift";
    cv.setAttribute("aria-hidden", "true");
    document.body.insertBefore(cv, document.body.firstChild);
    var ctx = cv.getContext("2d"),
      dpr = Math.min(window.devicePixelRatio || 1, 2),
      W = 0,
      H = 0,
      P = [];
    var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    function size() {
      W = window.innerWidth;
      H = window.innerHeight;
      cv.width = W * dpr;
      cv.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    size();
    window.addEventListener("resize", size);
    var n = W < 600 ? 9 : 18;
    for (var i = 0; i < n; i++) {
      var plus = Math.random() < 0.55;
      P.push({ x: Math.random() * W, y: Math.random() * H, r: 2 + Math.random() * 3.5, vx: (Math.random() - 0.5) * 0.12, vy: -0.03 - Math.random() * 0.08, ph: Math.random() * 6.28, c: plus ? "43,89,195" : "20,160,170" });
    }
    function draw(t) {
      ctx.clearRect(0, 0, W, H);
      P.forEach(function (p) {
        if (!still) {
          p.x += p.vx + Math.sin(t / 4000 + p.ph) * 0.05;
          p.y += p.vy;
          if (p.y < -12) p.y = H + 12;
          if (p.x < -12) p.x = W + 12;
          if (p.x > W + 12) p.x = -12;
        }
        var a = 0.10 + 0.08 * Math.sin(t / 1600 + p.ph);
        var g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 3);
        g.addColorStop(0, "rgba(" + p.c + "," + (a + 0.12).toFixed(3) + ")");
        g.addColorStop(0.35, "rgba(" + p.c + "," + a.toFixed(3) + ")");
        g.addColorStop(1, "rgba(" + p.c + ",0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * 3, 0, 6.283);
        ctx.fill();
      });
      if (!still && !document.hidden) requestAnimationFrame(draw);
    }
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && !still) requestAnimationFrame(draw);
    });
    requestAnimationFrame(draw);
  }

  // ---------- 시작 ----------
  // 본문·목차·퀴즈는 바로 쓸 수 있게 하고, 외부 라이브러리(CDN)는 기다리지 않는다.
  if (document.querySelector("section.hero")) document.body.classList.add("home");
  if (document.querySelector(".home-hero")) document.body.classList.add("home");
  if (document.querySelector("ol.roadmap")) document.body.classList.add("roadmap");
  if (document.querySelector(".paper-list")) document.body.classList.add("papers");
  setupSidebar();
  setupSearch();
  setupPapers();
  // setupDrift(); 홈 배경의 떠다니는 이온 장식은 끔(2026-10-31 요청: 학습과 관련 없는 장식 절제)
  setupPaperFigs();
  setupFigSizes();
  setupFigZoom();
  setupRecall();
  setupSteppers();
  setupLabs();
  setupFontSize();
  setupProgressBar();
  setupChapters();
  setupQuiz();
  setupSrcLinks();
  setupEmphasis();
  setupGlossary();
  setupCircled();
  setupProv();
  setupPaperTarget();
  setupCrossLinks();
  setupBrand();
  var depsP = deps();
  detectMode()
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
      setupBlankRecall();
      setupReadMode();
      setupToday();
      setupRoadmap();
      setupProjects();
      setupComments();
    });
  depsP.then(function () {
    // 마크다운·수식 라이브러리가 늦게 오면 그때 다시 그린다 (쓰는 중인 칸은 건드리지 않음)
    for (var k in EDITORS) {
      var ed = EDITORS[k];
      if (!(ed._ta && document.body.contains(ed._ta)) && ed.content) ed.renderView();
    }
    document.querySelectorAll(".quiz").forEach(typeset);
    // 그림 캡션은 HTML 블록이라 Pandoc이 수식으로 표시하지 않는다 → 여기서 조판
    document.querySelectorAll("figure.fig figcaption, .video .vcap, table.mvm-table").forEach(typeset);
  });
})();
