// 연구 노트 — 노션처럼 쓰는 페이지 모음. 사이트 열기(로컬 서버)로 열었을 때만 저장된다.
// 저장 위치: answers/notes/<id>.json (그림은 answers/notes/img/). 서버가 5분에 한 번씩 git에도 남긴다.
(function () {
  "use strict";
  var app = document.getElementById("notes-app");
  if (!app) return;

  var ICONS = ["📝", "🧪", "📄", "💡", "🔬", "⚡", "🧠", "📊", "🧲", "💧", "🌀", "📌", "✅", "❓", "🎯", "📚", "🗓️", "🔋", "🧬", "⭐"];
  var svg = function (d, w) {
    return '<svg viewBox="0 0 20 20" width="' + (w || 16) + '" height="' + (w || 16) + '" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + "</svg>";
  };
  var PEN = svg('<path d="M4 16h3l8.5-8.5a2.1 2.1 0 0 0-3-3L4 13v3z"/><path d="M11 6l3 3"/>', 17),
    LOUPE = svg('<circle cx="9" cy="9" r="5.5"/><path d="M13 13l4 4"/>', 14),
    BIN = svg('<path d="M4 6h12M8 6V4h4v2M6 6l.8 10h6.4L14 6"/>', 15),
    UNDO = svg('<path d="M5 8h7.5a3.5 3.5 0 0 1 0 7H9"/><path d="M8 5L5 8l3 3"/>', 15),
    DOC = svg('<path d="M5 3h7l3 3v11H5z"/><path d="M12 3v3h3M8 10h5M8 13h5"/>', 15),
    SIDE = svg('<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M8 4v12"/>', 17),
    CHEV = svg('<path d="M11.5 5.5L7 10l4.5 4.5M15.5 5.5L11 10l4.5 4.5"/>', 16),
    STAR = svg('<path d="M10 3.2l2.1 4.3 4.7.7-3.4 3.3.8 4.7L10 14l-4.2 2.2.8-4.7-3.4-3.3 4.7-.7z"/>', 16),
    STAR_ON = STAR.replace('fill="none"', 'fill="currentColor"'),
    DOTS = svg('<circle cx="5" cy="10" r=".9" fill="currentColor"/><circle cx="10" cy="10" r=".9" fill="currentColor"/><circle cx="15" cy="10" r=".9" fill="currentColor"/>', 17),
    SMILE = svg('<circle cx="10" cy="10" r="6.5"/><path d="M7.4 11.6c.7.9 1.6 1.4 2.6 1.4s1.9-.5 2.6-1.4"/><path d="M7.8 8.2h.01M12.2 8.2h.01" stroke-width="2"/>', 15),
    GRID = svg('<circle cx="6.5" cy="6.5" r="1.6"/><circle cx="13.5" cy="6.5" r="1.6"/><circle cx="6.5" cy="13.5" r="1.6"/><circle cx="13.5" cy="13.5" r="1.6"/>', 17),
    DOWN = svg('<path d="M10 3.5v9M6 9l4 4 4-4M4.5 16.5h11"/>', 15),
    KEYS = svg('<rect x="2.5" y="5" width="15" height="10" rx="2"/><path d="M5.5 8h.01M8.5 8h.01M11.5 8h.01M14.5 8h.01M6.5 12h7"/>', 15),
    PLUS = svg('<path d="M10 4.5v11M4.5 10h11"/>', 15);
  var BLOCKS = [
    { k: "p", label: "본문", hint: "그냥 글", key: "text body 본문 글" },
    { k: "h1", label: "제목 1", hint: "#", key: "h1 heading 제목1 큰" },
    { k: "h2", label: "제목 2", hint: "##", key: "h2 heading 제목2 중간" },
    { k: "h3", label: "제목 3", hint: "###", key: "h3 heading 제목3 작은" },
    { k: "ul", label: "글머리 목록", hint: "-", key: "bullet list ul 목록 글머리" },
    { k: "ol", label: "번호 목록", hint: "1.", key: "number list ol 번호" },
    { k: "todo", label: "할 일", hint: "[]", key: "todo check 할일 체크" },
    { k: "quote", label: "인용", hint: ">", key: "quote 인용" },
    { k: "callout", label: "콜아웃", hint: "강조 상자", key: "callout 콜아웃 강조 상자 메모" },
    { k: "pre", label: "코드·수식 줄", hint: "```", key: "code pre 코드 수식" },
    { k: "hr", label: "구분선", hint: "---", key: "divider hr 구분선 선" },
    { k: "img", label: "그림", hint: "사진 붙여넣기도 됨", key: "image img 그림 사진 이미지" }
  ];

  var state = { list: [], cur: null, q: "", trash: false, timer: null, rev: null };
  var esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  };
  function api(method, url, body) {
    return fetch(url, {
      method: method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      keepalive: method === "PUT" && body && JSON.stringify(body).length < 60000
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) {
          var e = new Error(j.error || r.status);
          e.status = r.status;
          e.body = j;
          throw e;
        }
        return j;
      });
    });
  }
  // ---------- 저장소: 사이트 서버(answers/notes)가 있으면 거기에, 없으면 이 브라우저(IndexedDB)에 ----------
  // 서버가 꺼져 있거나 예전 버전이어도 바로 쓸 수 있게 하고, 서버가 켜지면 브라우저에 쌓인 노트를 자동으로 옮긴다.
  var remote = false;
  var DB = null;
  function idb() {
    if (DB) return DB;
    DB = new Promise(function (res, rej) {
      var r = indexedDB.open("study-notes", 1);
      r.onupgradeneeded = function () { r.result.createObjectStore("notes", { keyPath: "id" }); };
      r.onsuccess = function () { res(r.result); };
      r.onerror = function () { rej(r.error); };
    });
    return DB;
  }
  function tx(mode, fn) {
    return idb().then(function (db) {
      return new Promise(function (res, rej) {
        var t = db.transaction("notes", mode), out;
        var q = fn(t.objectStore("notes"));
        if (q) q.onsuccess = function () { out = q.result; };
        t.oncomplete = function () { res(out); };
        t.onerror = function () { rej(t.error); };
      });
    });
  }
  function nowIso() {
    var d = new Date(), p = function (x) { return String(x).padStart(2, "0"); };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T" + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
  }
  function metaFrom(n) {
    var text = (n.html || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
    return { id: n.id, title: n.title, icon: n.icon, tags: n.tags, pinned: n.pinned, date: n.date, created: n.created, updated: n.updated, trashed: n.trashed, snippet: text.slice(0, 160) };
  }
  var store = {
    list: function () {
      if (remote) return api("GET", "/api/notes");
      return tx("readonly", function (st) { return st.getAll(); }).then(function (all) {
        return (all || []).map(metaFrom);
      });
    },
    get: function (id) {
      if (remote) return api("GET", "/api/notes/" + id);
      return tx("readonly", function (st) { return st.get(id); }).then(function (n) {
        if (!n) throw new Error("not found");
        return n;
      });
    },
    put: function (id, body) {
      if (remote) return api("PUT", "/api/notes/" + id, body);
      if (body.purge) return tx("readwrite", function (st) { return st["delete"](id); }).then(function () { return { ok: true }; });
      return tx("readonly", function (st) { return st.get(id); }).then(function (cur) {
        cur = cur || { id: id, created: nowIso() };
        ["title", "icon", "html", "tags", "pinned", "trashed", "date"].forEach(function (k) { if (k in body) cur[k] = body[k]; });
        if (!cur.trashed) delete cur.trashed;
        cur.updated = nowIso();
        cur.rev = Math.random().toString(36).slice(2, 10);
        return tx("readwrite", function (st) { return st.put(cur); }).then(function () {
          return { ok: true, rev: cur.rev, updated: cur.updated, created: cur.created };
        });
      });
    },
    img: function (data) {
      // 브라우저에 저장하는 동안은 그림을 노트 안에 그대로 넣고, 서버로 옮길 때 파일로 바꾼다
      if (remote) return api("PUT", "/api/notes-img", { data: data });
      return Promise.resolve({ url: data });
    }
  };
  function detect() {
    return fetch("/api/notes", { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function () { remote = true; }, function () { remote = false; });
  }
  // 브라우저에만 있던 노트를 서버로 옮긴다(그림은 파일로 올리고 주소를 바꿔서)
  function migrate() {
    return tx("readonly", function (st) { return st.getAll(); }).then(function (all) {
      all = all || [];
      return all.reduce(function (p, n) {
        return p.then(function () {
          var box = document.createElement("div");
          box.innerHTML = n.html || "";
          var imgs = Array.prototype.filter.call(box.querySelectorAll("img"), function (im) { return /^data:image\//.test(im.getAttribute("src")); });
          return imgs.reduce(function (q, im) {
            return q.then(function () {
              return api("PUT", "/api/notes-img", { data: im.getAttribute("src") }).then(function (r) { im.setAttribute("src", r.url); });
            });
          }, Promise.resolve()).then(function () {
            return api("PUT", "/api/notes/" + n.id, { title: n.title, icon: n.icon, html: box.innerHTML, tags: n.tags || [], pinned: !!n.pinned, date: n.date, trashed: n.trashed || false });
          }).then(function () {
            return tx("readwrite", function (st) { return st["delete"](n.id); });
          });
        });
      }, Promise.resolve()).then(function () { return all.length; });
    });
  }
  function banner() {
    var b = app.querySelector(".nt-banner");
    if (remote) {
      if (b) b.remove();
      return;
    }
    if (!b) {
      b = document.createElement("div");
      b.className = "nt-banner";
      app.insertBefore(b, app.firstChild);
    }
    b.textContent = "지금은 이 브라우저에 저장하고 있어요. 사이트 서버가 켜지면 answers/notes/ 폴더로 자동으로 옮겨집니다.";
  }
  function toast(t) {
    document.querySelectorAll(".nt-toast").forEach(function (x) { x.remove(); });
    var el = document.createElement("div");
    el.className = "nt-toast";
    el.textContent = t;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 4000);
  }
  function watchServer() {
    // 브라우저에 저장하는 중이면 30초마다 서버를 다시 확인해, 켜지면 옮기고 서버 저장으로 바꾼다
    setInterval(function () {
      if (remote) return;
      detect().then(function () {
        if (!remote) return;
        flush();
        migrate().then(function (k) {
          banner();
          loadList();
          if (k) toast("브라우저에 있던 노트 " + k + "개를 사이트 폴더로 옮겼어요.");
        });
      });
    }, 30000);
  }

  function newId() {
    return "n" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  }
  function today() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function noteDate(n) {
    return n.date || (n.created || "").slice(0, 10);
  }
  function shortDate(s) {
    if (!s) return "";
    var p = s.split("-");
    return +p[1] + "/" + +p[2];
  }

  // ---------- 붙여넣기·불러오기 때 남길 태그만(스크립트·이벤트 속성 제거) ----------
  var SIZES = [12, 14, 16, 20, 24, 32]; // 선택한 글자 크기 단계(px), 16 = 본문 기본
  var OK_TAGS = { P: 1, H1: 1, H2: 1, H3: 1, UL: 1, OL: 1, LI: 1, BLOCKQUOTE: 1, PRE: 1, CODE: 1, B: 1, STRONG: 1, I: 1, EM: 1, U: 1, S: 1, STRIKE: 1, A: 1, BR: 1, HR: 1, IMG: 1, SPAN: 1, MARK: 1, SUB: 1, SUP: 1, DIV: 1 };
  function clean(html) {
    var box = document.createElement("div");
    box.innerHTML = html;
    (function walk(el) {
      Array.prototype.slice.call(el.children).forEach(function (c) {
        walk(c);
        if (!OK_TAGS[c.tagName]) {
          if (/^(SCRIPT|STYLE|IFRAME|OBJECT|EMBED|META|LINK|TITLE)$/.test(c.tagName)) c.remove();
          else c.replaceWith.apply(c, Array.prototype.slice.call(c.childNodes));
          return;
        }
        var keep = {};
        if (c.tagName === "A" && /^https?:\/\//.test(c.getAttribute("href") || "")) keep.href = c.getAttribute("href");
        if (c.tagName === "IMG" && /^(\/api\/notes-img\/|https?:\/\/|data:image\/(png|jpeg|gif|webp);base64,)/.test(c.getAttribute("src") || "")) keep.src = c.getAttribute("src");
        if (c.tagName === "UL" && c.classList.contains("todo")) keep["class"] = "todo";
        if (c.tagName === "BLOCKQUOTE" && c.classList.contains("callout")) keep["class"] = "callout";
        if (c.tagName === "LI" && c.hasAttribute("data-done")) keep["data-done"] = "";
        if (c.tagName === "SPAN" || c.tagName === "MARK") {
          var bg = c.style.backgroundColor, fg = c.style.color, st = "";
          if (bg) st += "background-color:" + bg + ";";
          if (fg) st += "color:" + fg + ";";
          if (st) keep.style = st;
          if (c.tagName === "SPAN" && SIZES.indexOf(+c.getAttribute("data-fs")) >= 0) keep["data-fs"] = c.getAttribute("data-fs");
        }
        Array.prototype.slice.call(c.attributes).forEach(function (a) {
          c.removeAttribute(a.name);
        });
        Object.keys(keep).forEach(function (k) {
          c.setAttribute(k, keep[k]);
        });
        if (c.tagName === "IMG" && !c.getAttribute("src")) c.remove();
        if (c.tagName === "A") {
          c.target = "_blank";
          c.rel = "noopener";
        }
      });
    })(box);
    return box.innerHTML;
  }

  // ---------- 화면 뼈대(노션처럼: 왼쪽 페이지 목록, 오른쪽 문서) ----------
  app.innerHTML =
    '<div class="nt-side">' +
    '<div class="nt-side-top"><button type="button" class="nt-collapse nt-ibtn" title="목록 닫기 (Ctrl+\\)">' + SIDE + "</button>" +
    '<span class="nt-flex"></span>' +
    '<button type="button" class="nt-new nt-ibtn" title="새 페이지 (Ctrl+Alt+N)">' + PEN + "</button></div>" +
    '<label class="nt-search">' + LOUPE + '<input class="nt-q" type="search" placeholder="검색" aria-label="노트 검색"></label>' +
    '<div class="nt-list-wrap"><nav class="nt-list" aria-label="노트 목록"></nav>' +
    '<button type="button" class="nt-side-btn nt-add">' + PLUS + " 새 페이지 추가</button></div>" +
    '<div class="nt-side-foot"><button type="button" class="nt-ibtn nt-apps" title="더 보기" aria-label="더 보기" aria-haspopup="menu">' + GRID + "</button>" +
    '<div class="nt-apps-pop" hidden role="menu">' +
    '<button type="button" role="menuitem" class="nt-trash-btn">' + BIN + "<span>휴지통</span></button>" +
    '<button type="button" role="menuitem" class="nt-export">' + DOWN + "<span>모든 페이지 내보내기 (.md)</span></button>" +
    '<button type="button" role="menuitem" class="nt-keys-btn">' + KEYS + "<span>단축키</span></button>" +
    '<div class="nt-keys" hidden>' +
    "<div><kbd>Ctrl</kbd><kbd>S</kbd><span>저장</span></div>" +
    "<div><kbd>Ctrl</kbd><kbd>Alt</kbd><kbd>N</kbd><span>새 페이지</span></div>" +
    "<div><kbd>Ctrl</kbd><kbd>\\</kbd><span>목록 열기·닫기</span></div>" +
    "<div><kbd>/</kbd><span>블록 고르기</span></div>" +
    "<div><kbd>#</kbd><kbd>-</kbd><kbd>[]</kbd><kbd>&gt;</kbd><span>줄 맨 앞 서식</span></div>" +
    "<div><kbd>Ctrl</kbd><kbd>B</kbd><kbd>I</kbd><kbd>U</kbd><span>굵게·기울임·밑줄</span></div>" +
    "<div><kbd>Ctrl</kbd><kbd>Shift</kbd><kbd>&lt;</kbd><kbd>&gt;</kbd><span>선택한 글씨 작게·크게</span></div>" +
    "</div></div></div>" +
    "</div>" +
    '<div class="nt-scrim"></div>' +
    '<div class="nt-main"></div>' +
    '<div class="nt-menu" hidden role="listbox"></div>' +
    '<div class="nt-bubble" hidden>' +
    '<button type="button" data-c="bold" title="굵게 (Ctrl+B)"><b>B</b></button>' +
    '<button type="button" data-c="italic" title="기울임 (Ctrl+I)"><i>i</i></button>' +
    '<button type="button" data-c="underline" title="밑줄 (Ctrl+U)"><u>U</u></button>' +
    '<button type="button" data-c="strikeThrough" title="취소선"><s>S</s></button>' +
    '<button type="button" data-c="code" title="코드">&lt;/&gt;</button>' +
    '<button type="button" data-c="link" title="링크">↗</button>' +
    '<span class="nt-bsep"></span>' +
    '<button type="button" data-c="smaller" title="글씨 작게 (Ctrl+Shift+&lt;)" class="nt-fsz">A<small>−</small></button>' +
    '<button type="button" data-c="bigger" title="글씨 크게 (Ctrl+Shift+&gt;)" class="nt-fsz nt-fsz-up">A<small>+</small></button>' +
    '<span class="nt-bsep"></span>' +
    '<button type="button" data-c="hl" title="노란 배경"><span class="nt-hl-ico">A</span></button>' +
    '<button type="button" data-c="red" title="빨간 글자"><span style="color:#d44c47">A</span></button>' +
    '<button type="button" data-c="clear" title="서식 지우기">⌫</button>' +
    "</div>" +
    '<input type="file" accept="image/*" class="nt-file" hidden>';
  var side = app.querySelector(".nt-side"),
    listEl = app.querySelector(".nt-list"),
    qEl = app.querySelector(".nt-q"),
    main = app.querySelector(".nt-main"),
    menu = app.querySelector(".nt-menu"),
    bubble = app.querySelector(".nt-bubble"),
    fileIn = app.querySelector(".nt-file");
  var body = null; // 지금 편집 중인 본문(.nt-body)
  // 위 메뉴 막대 아래를 꽉 채운다
  function fit() {
    var nb = document.querySelector("#quarto-header");
    app.style.setProperty("--nt-top", (nb ? nb.getBoundingClientRect().bottom : 0) + "px");
  }
  fit();
  window.addEventListener("resize", fit);

  // ---------- 목록 ----------
  function itemHtml(n) {
    return '<a class="nt-item' + (state.cur && state.cur.id === n.id ? " on" : "") + '" href="#' + n.id + '" data-id="' + n.id + '">' +
      '<span class="nt-ico">' + (n.icon ? esc(n.icon) : DOC) + "</span>" +
      '<span class="nt-t">' + esc(n.title || "제목 없음") + "</span>" +
      // 마우스를 올리면 보이는 버튼: 목록에서는 휴지통으로, 휴지통에서는 복원·영구 삭제
      (n.trashed
        ? '<span class="nt-act" role="button" data-act="restore" title="복원">' + UNDO + "</span>" +
          '<span class="nt-act" role="button" data-act="purge" title="영구 삭제">' + BIN + "</span>"
        : '<span class="nt-act" role="button" data-act="trash" title="휴지통으로 이동">' + BIN + "</span>") +
      "</a>";
  }
  // 페이지를 휴지통으로 옮기거나(when) 되살린다(false). 지금 열린 페이지면 화면도 맞춰 바꾼다.
  function setTrashed(id, when) {
    var isCur = state.cur && state.cur.id === id;
    if (isCur) flush();
    var p = isCur ? save({ trashed: when }) : store.put(id, { trashed: when }).then(function (r) {
      var m = metaOf(id);
      if (m) {
        m.trashed = when || undefined;
        m.updated = r.updated;
      }
      return true;
    });
    return p.then(function (ok) {
      if (!ok) return;
      if (when) {
        toast("휴지통으로 옮겼어요. 왼쪽 아래 메뉴의 휴지통에서 복원할 수 있어요.");
        if (isCur) {
          var rest = state.list.filter(function (n) { return !n.trashed; });
          if (rest.length) location.hash = rest[rest.length - 1].id;
          else newPage();
          return;
        }
      } else {
        toast("복원했어요.");
        if (isCur) return open(id);
      }
      renderList();
    }).catch(function () {
      toast("바꾸지 못했어요. 잠시 뒤 다시 해 보세요.");
    });
  }
  function purgeNote(id) {
    var m = metaOf(id);
    if (!confirm("‘" + ((m && m.title) || "제목 없음") + "’ 페이지를 영구 삭제할까요? 되돌릴 수 없어요.")) return;
    store.put(id, { purge: true }).then(function () {
      state.list = state.list.filter(function (n) { return n.id !== id; });
      toast("영구 삭제했어요.");
      if (state.cur && state.cur.id === id) newPage();
      else renderList();
    }).catch(function () {
      toast("삭제하지 못했어요.");
    });
  }
  function renderList() {
    var q = state.q.toLowerCase();
    var items = state.list.filter(function (n) {
      if (!!n.trashed !== state.trash) return false;
      if (q && ((n.title || "") + " " + (n.snippet || "")).toLowerCase().indexOf(q) < 0) return false;
      return true;
    });
    items.sort(function (a, b) {
      return (a.created || "").localeCompare(b.created || "");
    });
    var h = "";
    if (state.trash) {
      h += '<div class="nt-group">휴지통<button type="button" class="nt-back-list">닫기</button></div>';
      h += items.map(itemHtml).join("");
    } else {
      var fav = items.filter(function (n) { return n.pinned; });
      if (fav.length) h += '<div class="nt-group">즐겨찾기</div>' + fav.map(itemHtml).join("");
      h += '<div class="nt-group">' + (q ? "검색 결과" : "모든 노트") + "</div>" + items.map(itemHtml).join("");
    }
    if (!items.length) h += '<p class="nt-none">' + (state.trash ? "휴지통이 비어 있어요." : q ? "맞는 페이지가 없어요." : "") + "</p>";
    listEl.innerHTML = h;
  }
  function loadList() {
    return store.list().then(function (l) {
      state.list = l;
      renderList();
    });
  }
  function metaOf(id) {
    for (var i = 0; i < state.list.length; i++) if (state.list[i].id === id) return state.list[i];
    return null;
  }

  // ---------- 새 페이지: 바로 빈 문서가 열리고, 무언가 적으면 그때 저장된다 ----------
  var creating = false;
  function newPage() {
    if (creating) return;
    creating = true;
    flush();
    state.trash = false;
    var n = { id: newId(), title: "", icon: "", tags: [], html: "<p><br></p>", date: today() };
    store.put(n.id, n).then(function (r) {
      n.rev = r.rev;
      n.created = r.created;
      n.updated = r.updated;
      state.list.push({ id: n.id, title: "", icon: "", created: r.created, updated: r.updated, date: n.date, snippet: "" });
      state.cur = n;
      state.rev = r.rev;
      history.replaceState(null, "", "#" + n.id);
      renderPage();
      renderList();
      closeSide();
      main.querySelector(".nt-title").focus();
    }).catch(function () {
      toast("새 페이지를 만들지 못했어요.");
    }).then(function () {
      creating = false;
    });
  }
  function showEmpty() {
    newPage();
  }

  // ---------- 페이지 열기 ----------
  function open(id) {
    flush();
    return store.get(id).then(function (n) {
      state.cur = n;
      state.rev = n.rev;
      if (n.trashed) state.trash = true;
      renderPage();
      renderList();
      closeSide();
    }).catch(function () {
      newPage();
    });
  }
  function closeSide() {
    app.classList.remove("side-open");
  }

  function ago(iso) {
    if (!iso) return "";
    var m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (m < 1) return "방금 편집";
    if (m < 60) return m + "분 전 편집";
    if (m < 60 * 24) return Math.round(m / 60) + "시간 전 편집";
    return iso.slice(0, 10).replace(/-/g, ". ") + " 편집";
  }
  setInterval(function () {
    if (state.cur && !state.timer) setSaved(ago(state.cur.updated));
  }, 60000);

  function crumb(n) {
    return (n.icon ? '<span class="nt-crumb-ico">' + esc(n.icon) + "</span>" : "") + '<span class="nt-crumb-t">' + esc(n.title || "제목 없음") + "</span>";
  }
  function metaLine(n) {
    var c = (n.created || "").replace("T", " ").slice(0, 16).replace(/-/g, ". ");
    var u = (n.updated || "").replace("T", " ").slice(0, 16).replace(/-/g, ". ");
    return (c ? "<div><span>만든 때</span>" + c + "</div>" : "") + (u ? "<div><span>마지막 수정</span>" + u + "</div>" : "");
  }
  // 오른쪽 목차: 제목이 2개 이상이면 가는 줄로, 마우스를 올리면 제목 목록(노션처럼)
  function buildToc() {
    var box = main.querySelector(".nt-toc");
    if (!box || !body) return;
    var hs = Array.prototype.filter.call(body.querySelectorAll("h1, h2, h3"), function (h) { return h.textContent.trim(); });
    box.hidden = hs.length < 2;
    box.innerHTML = '<div class="nt-toc-lines">' + hs.map(function (h) { return '<i class="l' + h.nodeName[1] + '"></i>'; }).join("") + "</div>" +
      '<div class="nt-toc-pop">' + hs.map(function (h, i) { return '<button type="button" class="l' + h.nodeName[1] + '" data-i="' + i + '">' + esc(h.textContent.trim()) + "</button>"; }).join("") + "</div>";
    box.onclick = function (e) {
      var b = e.target.closest("button");
      if (b) hs[+b.dataset.i].scrollIntoView({ behavior: "smooth", block: "start" });
    };
  }

  function renderPage() {
    var n = state.cur;
    var tr = !!n.trashed;
    main.innerHTML =
      '<div class="nt-top">' +
      '<button type="button" class="nt-ibtn nt-to-list" aria-label="페이지 목록">' + SIDE + "</button>" +
      '<span class="nt-crumb">' + crumb(n) + "</span>" +
      '<span class="nt-saved"></span>' +
      (tr ? "" : '<button type="button" class="nt-save" data-a="save" title="저장 (Ctrl+S)">저장</button>') +
      (tr ? "" : '<button type="button" class="nt-ibtn nt-fav' + (n.pinned ? " on" : "") + '" data-a="pin" title="즐겨찾기" aria-pressed="' + !!n.pinned + '">' + (n.pinned ? STAR_ON : STAR) + "</button>" +
        '<span class="nt-more-wrap"><button type="button" class="nt-ibtn" data-a="more" title="더 보기" aria-label="더 보기">' + DOTS + "</button>" +
        '<div class="nt-pop" hidden><div class="nt-info">' + metaLine(n) + '</div><button type="button" data-a="md">마크다운으로 복사</button><button type="button" data-a="trash">휴지통으로 이동</button></div></span>') +
      "</div>" +
      '<div class="nt-scroll">' +
      (tr ? '<div class="nt-trash-bar">이 페이지는 휴지통에 있어요.<button type="button" data-a="restore">복원</button><button type="button" data-a="purge">영구 삭제</button></div>' : "") +
      '<article class="nt-page">' +
      (n.icon ? '<button type="button" class="nt-icon" title="아이콘 바꾸기">' + esc(n.icon) + "</button>" : "") +
      (tr ? "" : '<div class="nt-page-ctl">' + (n.icon ? "" : '<button type="button" class="nt-add-icon">' + SMILE + " 아이콘 추가</button>") + "</div>") +
      '<div class="nt-icons" hidden>' + ICONS.map(function (i) { return '<button type="button">' + i + "</button>"; }).join("") +
      '<button type="button" class="nt-icon-none">없음</button></div>' +
      '<h1 class="nt-title" contenteditable="' + !tr + '" spellcheck="false" data-ph="제목 없음">' + esc(n.title || "") + "</h1>" +

      '<div class="nt-body" contenteditable="' + !tr + '" spellcheck="false">' + clean(n.html || "<p></p>") + "</div>" +
      "</article></div>" +
      '<nav class="nt-toc" hidden aria-label="이 페이지 목차"></nav>';
    body = main.querySelector(".nt-body");
    document.execCommand("defaultParagraphSeparator", false, "p");
    if (!body.firstElementChild) body.innerHTML = "<p><br></p>";
    setSaved(n._new ? "" : ago(n.updated));
    buildToc();
  }

  // ---------- 저장(입력이 멈추고 0.7초 뒤 자동) ----------
  function setSaved(t) {
    var s = main.querySelector(".nt-saved");
    if (s) s.textContent = t;
  }
  function snapshot() {
    var n = state.cur;
    var h = body.cloneNode(true);
    h.querySelectorAll("[data-ph]").forEach(function (x) { x.removeAttribute("data-ph"); });
    return { title: main.querySelector(".nt-title").textContent.trim(), icon: n.icon, tags: n.tags || [], html: clean(h.innerHTML), date: n.date, pinned: !!n.pinned };
  }
  function schedule() {
    if (!state.cur || state.cur.trashed) return;
    setSaved("저장 중…");
    clearTimeout(state.timer);
    state.timer = setTimeout(save, 700);
  }
  function flush() {
    if (state.timer) {
      clearTimeout(state.timer);
      state.timer = null;
      save();
    }
  }
  function save(extra) {
    state.timer = null;
    if (!state.cur) return Promise.resolve();
    var n = state.cur;
    var data = n.trashed ? {} : snapshot();
    Object.keys(extra || {}).forEach(function (k) { data[k] = extra[k]; });
    data.base_rev = state.rev;
    setSaved("저장 중…");
    return store.put(n.id, data).then(function (r) {
      if (state.cur !== n) return true;
      state.rev = r.rev;
      Object.keys(data).forEach(function (k) { if (k !== "base_rev" && k !== "html") n[k] = data[k]; });
      n.updated = r.updated;
      if (n._new) {
        delete n._new;
        n.created = r.created;
        state.list.push({ id: n.id, created: r.created });
        history.replaceState(null, "", "#" + n.id);
      }
      var m = metaOf(n.id);
      if (m) {
        ["title", "icon", "tags", "date", "pinned", "trashed"].forEach(function (k) { m[k] = n[k]; });
        m.updated = r.updated;
        if (body) m.snippet = body.textContent.replace(/\s+/g, " ").trim().slice(0, 160);
      }
      setSaved(ago(r.updated));
      buildToc();
      var ct = main.querySelector(".nt-crumb");
      if (ct) ct.innerHTML = crumb(n);
      var mt = main.querySelector(".nt-info");
      if (mt) mt.innerHTML = metaLine(n);
      renderList();
      return true;
    }).catch(function (e) {
      if (e.status === 409) {
        setSaved("");
        if (confirm("다른 탭(창)에서 이 노트가 먼저 바뀌었어요. [확인] = 이 화면 내용으로 덮어쓰기, [취소] = 저장된 내용 다시 불러오기")) {
          state.rev = e.body.note.rev;
          return save(extra);
        }
        open(n.id);
        return false;
      }
      setSaved("⚠ 저장하지 못했어요");
      return false;
    });
  }
  // 저장 버튼·Ctrl+S: 기다리지 않고 바로 저장
  function saveNow() {
    if (!state.cur || state.cur.trashed) return;
    clearTimeout(state.timer);
    state.timer = null;
    save().then(function (ok) {
      toast(ok ? (remote ? "저장했어요" : "이 브라우저에 저장했어요") : "저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    });
  }
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      saveNow();
    }
  });
  window.addEventListener("beforeunload", flush);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flush();
  });

  // ---------- 편집 도우미 ----------
  function curBlock() {
    var s = window.getSelection();
    if (!s.rangeCount || !body) return null;
    var n = s.anchorNode;
    if (!body.contains(n)) return null;
    while (n && n.parentNode !== body) {
      if (n.nodeName === "LI") return n;
      n = n.parentNode;
    }
    return n && n.nodeType === 1 ? n : null;
  }
  function caretToEnd(el) {
    var r = document.createRange();
    r.selectNodeContents(el);
    r.collapse(false);
    var s = window.getSelection();
    s.removeAllRanges();
    s.addRange(r);
  }
  function caretRect() {
    var s = window.getSelection();
    if (!s.rangeCount) return null;
    var r = s.getRangeAt(0).cloneRange();
    var rects = r.getClientRects();
    if (rects.length) return rects[rects.length - 1];
    var b = curBlock();
    return b ? b.getBoundingClientRect() : null;
  }
  function stripPrefix(block, len) {
    // 블록 맨 앞 len 글자(# , - 같은 단축 기호)를 지운다
    var w = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    var t = w.nextNode();
    if (t) t.textContent = t.textContent.slice(len);
  }
  function setBlock(kind) {
    var b = curBlock();
    document.execCommand("defaultParagraphSeparator", false, "p");
    if (kind === "hr") {
      var hr = document.createElement("hr"), p = document.createElement("p");
      p.innerHTML = "<br>";
      var top = b && b.nodeName === "LI" ? b.closest("ul,ol") : b;
      if (top && top.parentNode === body) {
        if (top.textContent.trim() === "" && top.nodeName !== "UL" && top.nodeName !== "OL") top.replaceWith(hr);
        else top.after(hr);
      } else body.appendChild(hr);
      hr.after(p);
      caretToEnd(p);
      return;
    }
    if (kind === "img") {
      fileIn.value = "";
      fileIn.click();
      return;
    }
    if (!b) return;
    // execCommand의 목록·formatBlock은 <p> 안에 <ul>을 넣는 등 구조를 망가뜨려서 직접 바꾼다
    var isList = kind === "ul" || kind === "ol" || kind === "todo";
    var tag = isList ? (kind === "ol" ? "OL" : "UL") : ({ quote: "BLOCKQUOTE", callout: "BLOCKQUOTE", pre: "PRE" }[kind] || kind.toUpperCase());
    var target;
    if (b.nodeName === "LI") {
      var list = b.parentNode;
      if (isList) {
        // 목록 종류만 바꾼다(목록 전체)
        var nl = list;
        if (list.nodeName !== tag) {
          nl = document.createElement(tag);
          while (list.firstChild) nl.appendChild(list.firstChild);
          list.replaceWith(nl);
        }
        nl.classList.toggle("todo", kind === "todo");
        if (!nl.classList.length) nl.removeAttribute("class");
        caretToEnd(b);
        return;
      }
      // 항목 하나를 목록 밖으로 꺼내 블록으로(목록은 앞뒤로 나뉜다)
      var after = document.createElement(list.nodeName);
      if (list.className) after.className = list.className;
      while (b.nextSibling) after.appendChild(b.nextSibling);
      target = document.createElement(tag);
      while (b.firstChild) target.appendChild(b.firstChild);
      b.remove();
      var anchor = list.parentNode === body ? list : list.closest("ul,ol");
      anchor.after(target);
      if (after.children.length) target.after(after);
      if (!list.children.length) list.remove();
    } else if (isList) {
      var li = document.createElement("li");
      while (b.firstChild) li.appendChild(b.firstChild);
      var prev = b.previousElementSibling;
      if (prev && prev.nodeName === tag && prev.classList.contains("todo") === (kind === "todo")) {
        prev.appendChild(li);
        b.remove();
      } else {
        var l2 = document.createElement(tag);
        if (kind === "todo") l2.className = "todo";
        l2.appendChild(li);
        b.replaceWith(l2);
      }
      target = li;
    } else {
      target = document.createElement(tag);
      while (b.firstChild) target.appendChild(b.firstChild);
      b.replaceWith(target);
    }
    if (kind === "callout") target.className = "callout";
    if (!target.textContent && !target.querySelector("img")) target.innerHTML = "<br>";
    caretToEnd(target);
  }

  // ---------- / 메뉴 ----------
  var slash = null; // {block, start}
  function openMenu() {
    var r = caretRect();
    if (!r) return;
    slash = { sel: 0 };
    drawMenu("");
    menu.hidden = false;
    var top = r.bottom + 6, left = r.left;
    var mh = Math.min(menu.offsetHeight, 330);
    if (top + mh > window.innerHeight - 8) top = Math.max(8, r.top - mh - 6);
    menu.style.top = top + "px";
    menu.style.left = Math.min(left, window.innerWidth - 260) + "px";
  }
  function closeMenu() {
    slash = null;
    menu.hidden = true;
  }
  function slashQuery() {
    // 캐럿 바로 앞의 "/검색어"
    var s = window.getSelection();
    if (!s.rangeCount) return null;
    var n = s.anchorNode, o = s.anchorOffset;
    if (!n || n.nodeType !== 3) return null;
    var before = n.textContent.slice(0, o);
    var i = before.lastIndexOf("/");
    if (i < 0 || /\s/.test(before.slice(i + 1)) || before.length - i > 14) return null;
    return { node: n, start: i, end: o, q: before.slice(i + 1) };
  }
  function drawMenu(q) {
    q = q.toLowerCase();
    var items = BLOCKS.filter(function (b) {
      return !q || (b.label + " " + b.key).toLowerCase().indexOf(q) >= 0;
    });
    slash.items = items;
    if (slash.sel >= items.length) slash.sel = 0;
    menu.innerHTML = items.length
      ? '<div class="nt-menu-h">블록</div>' + items.map(function (b, i) {
          return '<button type="button" class="' + (i === slash.sel ? "on" : "") + '" data-i="' + i + '"><span class="nt-mi">' + menuIcon(b.k) + "</span><span>" + b.label + '</span><small>' + esc(b.hint) + "</small></button>";
        }).join("")
      : '<div class="nt-menu-h">맞는 블록 없음</div>';
  }
  function menuIcon(k) {
    return { p: "¶", h1: "H1", h2: "H2", h3: "H3", ul: "•", ol: "1.", todo: "☑", quote: "❝", callout: "💡", pre: "{ }", hr: "—", img: "🖼" }[k];
  }
  function pick(i) {
    var b = slash && slash.items[i];
    var sq = slashQuery();
    closeMenu();
    if (!b) return;
    if (sq) {
      var r = document.createRange();
      r.setStart(sq.node, sq.start);
      r.setEnd(sq.node, sq.end);
      r.deleteContents();
    }
    var blk = curBlock();
    if (blk && !blk.textContent && !blk.querySelector("br,img")) blk.innerHTML = "<br>";
    setBlock(b.k);
    schedule();
  }
  menu.addEventListener("mousedown", function (e) {
    e.preventDefault();
    var b = e.target.closest("button");
    if (b) pick(+b.dataset.i);
  });

  // ---------- 선택하면 뜨는 서식 도구 ----------
  function showBubble() {
    var s = window.getSelection();
    if (!body || !s.rangeCount || s.isCollapsed || !body.contains(s.anchorNode) || state.cur.trashed) {
      bubble.hidden = true;
      return;
    }
    var r = s.getRangeAt(0).getBoundingClientRect();
    bubble.hidden = false;
    bubble.style.top = Math.max(8, r.top - bubble.offsetHeight - 8) + "px";
    bubble.style.left = Math.max(8, Math.min(r.left + r.width / 2 - bubble.offsetWidth / 2, window.innerWidth - bubble.offsetWidth - 8)) + "px";
  }
  document.addEventListener("selectionchange", function () {
    showBubble();
    markEmpty();
  });
  bubble.addEventListener("mousedown", function (e) {
    e.preventDefault();
    var b = e.target.closest("button");
    if (!b) return;
    var c = b.dataset.c;
    document.execCommand("styleWithCSS", false, c === "hl" || c === "red");
    if (c === "hl") document.execCommand("hiliteColor", false, "#fdf0b8");
    else if (c === "red") document.execCommand("foreColor", false, "#d4380d");
    else if (c === "code") {
      var s = window.getSelection();
      var t = s.toString();
      document.execCommand("insertHTML", false, "<code>" + esc(t) + "</code>");
    } else if (c === "link") {
      var url = prompt("링크 주소 (https://…)");
      if (url && /^https?:\/\//.test(url)) document.execCommand("createLink", false, url);
    } else if (c === "bigger" || c === "smaller") {
      resize(c === "bigger" ? 1 : -1);
    } else if (c === "clear") {
      var sel = window.getSelection(), keep = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
      document.execCommand("removeFormat");
      document.execCommand("unlink");
      // 지울 서식이 없으면 선택이 풀리기도 해서 되살린 뒤 크기도 기본으로
      if (keep && sel.isCollapsed) {
        sel.removeAllRanges();
        sel.addRange(keep);
      }
      applySize(16);
    } else document.execCommand(c);
    document.execCommand("styleWithCSS", false, false);
    schedule();
    showBubble();
  });

  // 선택한 글자 크기: <span data-fs="20">처럼 단계값만 저장(크기는 CSS가 정함)
  function resize(dir) {
    var s = window.getSelection();
    if (!s.rangeCount) return;
    // 선택 안의 첫 글자 크기 기준(선택 시작이 블록 경계일 수 있어서)
    var rg = s.getRangeAt(0), n = rg.startContainer;
    var w = document.createTreeWalker(rg.commonAncestorContainer, NodeFilter.SHOW_TEXT);
    for (var t = w.nextNode(); t; t = w.nextNode()) {
      if (t.textContent.trim() && rg.intersectsNode(t)) {
        n = t;
        break;
      }
    }
    var now = parseFloat(getComputedStyle(n.nodeType === 1 ? n : n.parentNode).fontSize);
    var next = dir > 0
      ? SIZES.filter(function (x) { return x > now + 0.5; })[0]
      : SIZES.filter(function (x) { return x < now - 0.5; }).pop();
    if (next) applySize(next);
  }
  function applySize(px) {
    var s = window.getSelection();
    if (!body || !s.rangeCount || s.isCollapsed || !body.contains(s.anchorNode)) return;
    // fontSize 명령으로 선택을 <font>로 감싼 뒤 우리 형식의 span으로 바꾼다
    document.execCommand("styleWithCSS", false, false);
    document.execCommand("fontSize", false, "7");
    var made = Array.prototype.slice.call(body.querySelectorAll('font[size="7"]')).map(function (f) {
      var sp = document.createElement("span");
      while (f.firstChild) sp.appendChild(f.firstChild);
      f.replaceWith(sp);
      Array.prototype.slice.call(sp.querySelectorAll("[data-fs]")).forEach(function (d) {
        d.removeAttribute("data-fs");
      });
      // 이미 크기를 준 span을 통째로 다시 고르면 겹치지 않게 바깥 span 하나로 합친다
      var pa = sp.parentNode;
      while (pa.nodeName === "SPAN" && pa !== body && pa.childNodes.length === 1 && pa.attributes.length <= 1 && (pa.attributes.length === 0 || pa.hasAttribute("data-fs"))) {
        pa.removeAttribute("data-fs");
        pa.removeChild(sp);
        while (sp.firstChild) pa.appendChild(sp.firstChild);
        sp = pa;
        pa = sp.parentNode;
      }
      var outer = pa.closest("[data-fs]");
      if (px !== 16 || (outer && body.contains(outer))) sp.setAttribute("data-fs", px);
      return sp;
    });
    if (!made.length) return;
    var r = document.createRange();
    r.setStartBefore(made[0]);
    r.setEndAfter(made[made.length - 1]);
    s.removeAllRanges();
    s.addRange(r);
  }

  // 빈 줄에 안내 글(포커스된 빈 블록에만)
  var lastPh = null;
  function markEmpty() {
    if (lastPh) lastPh.removeAttribute("data-ph");
    lastPh = null;
    var b = curBlock();
    if (b && b.textContent === "" && !b.querySelector("img") && b.nodeName !== "HR") {
      b.setAttribute("data-ph", b.nodeName === "LI" ? "목록" : /^H\d$/.test(b.nodeName) ? "제목" : "‘/’를 눌러 블록 고르기");
      lastPh = b;
    }
  }

  // ---------- 그림 ----------
  function shrink(file) {
    // 긴 변 2000px, JPEG로 줄여서 올린다(폰 사진 그대로면 수 MB)
    return new Promise(function (res, rej) {
      var fr = new FileReader();
      fr.onerror = rej;
      fr.onload = function () {
        if (file.size < 600000 && file.type !== "image/heic") return res(fr.result);
        var im = new Image();
        im.onerror = function () { res(fr.result); };
        im.onload = function () {
          var k = Math.min(1, 2000 / Math.max(im.width, im.height));
          var cv = document.createElement("canvas");
          cv.width = Math.round(im.width * k);
          cv.height = Math.round(im.height * k);
          var cx = cv.getContext("2d");
          cx.fillStyle = "#fff";
          cx.fillRect(0, 0, cv.width, cv.height);
          cx.drawImage(im, 0, 0, cv.width, cv.height);
          res(cv.toDataURL("image/jpeg", 0.86));
        };
        im.src = fr.result;
      };
      fr.readAsDataURL(file);
    });
  }
  function insertImages(files) {
    files = Array.prototype.filter.call(files, function (f) { return /^image\//.test(f.type); });
    if (!files.length) return false;
    setSaved("그림 올리는 중…");
    files.reduce(function (p, f) {
      return p.then(function () {
        return shrink(f).then(function (d) {
          return store.img(d);
        }).then(function (r) {
          body.focus();
          document.execCommand("insertHTML", false, '<p><img src="' + r.url + '" alt=""></p><p><br></p>');
        });
      });
    }, Promise.resolve()).then(schedule).catch(function () {
      setSaved("⚠ 그림을 올리지 못했어요");
    });
    return true;
  }
  fileIn.addEventListener("change", function () {
    insertImages(fileIn.files);
  });

  // ---------- 본문 입력 ----------
  main.addEventListener("keydown", function (e) {
    if (e.target.classList.contains("nt-title")) {
      if (e.key === "Enter") {
        e.preventDefault();
        body.focus();
        var r0 = document.createRange(), s0 = window.getSelection();
        r0.setStart(body.firstElementChild || body, 0);
        r0.collapse(true);
        s0.removeAllRanges();
        s0.addRange(r0);
      }
      return;
    }
    if (e.target !== body) return;
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.code === "Period" || e.code === "Comma")) {
      e.preventDefault();
      resize(e.code === "Period" ? 1 : -1);
      schedule();
      showBubble();
      return;
    }
    if (slash && !menu.hidden) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        var n = slash.items.length;
        if (n) slash.sel = (slash.sel + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
        drawMenu(slashQuery() ? slashQuery().q : "");
        return;
      }
      if (e.key === "Enter" && !e.isComposing) {
        e.preventDefault();
        pick(slash.sel);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        closeMenu();
        return;
      }
    }
    var b = curBlock();
    if (e.key === "Tab" && b && b.nodeName === "LI") {
      e.preventDefault();
      document.execCommand(e.shiftKey ? "outdent" : "indent");
      schedule();
      return;
    }
    // 빈 제목·인용·코드 줄에서 Backspace → 본문으로
    if (e.key === "Backspace" && b && b.textContent === "" && /^(H1|H2|H3|BLOCKQUOTE|PRE)$/.test(b.nodeName)) {
      e.preventDefault();
      setBlock("p");
      schedule();
      return;
    }
    // 제목·인용 끝에서 Enter → 다음 줄은 본문
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && b && /^(H1|H2|H3)$/.test(b.nodeName)) {
      var s = window.getSelection(), r = document.createRange();
      r.selectNodeContents(b);
      r.setStart(s.anchorNode, s.anchorOffset);
      if (r.toString() === "") {
        e.preventDefault();
        var p = document.createElement("p");
        p.innerHTML = "<br>";
        b.after(p);
        caretToEnd(p);
        schedule();
      }
    }
    // 코드 줄 안 Enter는 줄바꿈만
    if (e.key === "Enter" && b && b.nodeName === "PRE" && !e.shiftKey) {
      e.preventDefault();
      document.execCommand("insertText", false, "\n");
    }
  });
  main.addEventListener("input", function (e) {
    if (e.target.classList.contains("nt-title")) {
      // 저장을 기다리지 않고 왼쪽 목록·위 막대 제목을 바로 바꾼다
      var tt = e.target.textContent.trim() || "제목 없음";
      var li = side.querySelector('.nt-item[data-id="' + state.cur.id + '"] .nt-t');
      if (li) li.textContent = tt;
      var ct = main.querySelector(".nt-crumb-t");
      if (ct) ct.textContent = tt;
      schedule();
      return;
    }
    if (e.target !== body) return;
    var b = curBlock();
    // 마크다운 단축키: 줄 맨 앞에서 '# ' '- ' '1. ' '[] ' '> ' '```' '---'
    if (b && e.inputType === "insertText" && b.nodeName !== "PRE") {
      var t = b.textContent;
      var rules = [
        [/^###\s$/, "h3"], [/^##\s$/, "h2"], [/^#\s$/, "h1"], [/^[-*]\s$/, "ul"], [/^1[.)]\s$/, "ol"],
        [/^\[\s?\]\s$/, "todo"], [/^>\s$/, "quote"], [/^!\s$/, "callout"], [/^```$/, "pre"], [/^---$/, "hr"]
      ];
      for (var i = 0; i < rules.length; i++) {
        if (rules[i][0].test(t.replace(/ /g, " ")) && !(b.nodeName === "LI" && /^(ul|ol|todo)$/.test(rules[i][1]))) {
          stripPrefix(b, t.length);
          if (!b.textContent) b.innerHTML = "<br>";
          caretToEnd(b);
          setBlock(rules[i][1]);
          break;
        }
      }
    }
    var sq = slashQuery();
    if (sq && !slash && e.data && e.data.indexOf("/") >= 0) openMenu();
    if (slash) {
      if (!sq) closeMenu();
      else drawMenu(sq.q);
    }
    if (!body.firstElementChild) body.innerHTML = "<p><br></p>";
    markEmpty();
    schedule();
  });
  // 할 일 체크: 항목 왼쪽 네모를 누르면
  main.addEventListener("mousedown", function (e) {
    var li = e.target.closest && e.target.closest("ul.todo > li");
    if (!li || !body || !body.contains(li) || state.cur.trashed) return;
    var x = e.clientX - li.getBoundingClientRect().left;
    if (x < 0 && x > -28) {
      e.preventDefault();
      if (li.hasAttribute("data-done")) li.removeAttribute("data-done");
      else li.setAttribute("data-done", "");
      schedule();
    }
  });
  main.addEventListener("paste", function (e) {
    if (e.target.closest && e.target.closest(".nt-title")) {
      e.preventDefault();
      document.execCommand("insertText", false, (e.clipboardData.getData("text/plain") || "").replace(/\s+/g, " "));
      return;
    }
    if (!body || !body.contains(e.target)) return;
    var cd = e.clipboardData;
    if (cd.files && cd.files.length && insertImages(cd.files)) {
      e.preventDefault();
      return;
    }
    var h = cd.getData("text/html");
    if (h) {
      e.preventDefault();
      document.execCommand("insertHTML", false, clean(h));
    }
  });
  main.addEventListener("drop", function (e) {
    if (!body || !body.contains(e.target) || !e.dataTransfer.files.length) return;
    e.preventDefault();
    var pos = document.caretRangeFromPoint && document.caretRangeFromPoint(e.clientX, e.clientY);
    if (pos) {
      var s = window.getSelection();
      s.removeAllRanges();
      s.addRange(pos);
    }
    insertImages(e.dataTransfer.files);
  });

  // ---------- 버튼 ----------
  function iconPick(show) {
    var box = main.querySelector(".nt-icons");
    if (box) box.hidden = show === undefined ? !box.hidden : !show;
  }
  main.addEventListener("click", function (e) {
    var t = e.target.closest("button");
    var pop = main.querySelector(".nt-pop");
    if (pop && !(t && t.dataset.a === "more")) pop.hidden = true;
    if (!t) return;
    if (t.classList.contains("nt-to-list")) {
      if (window.innerWidth < 768) app.classList.toggle("side-open");
      else setSideClosed(false);
      return;
    }
    if ((t.classList.contains("nt-icon") || t.classList.contains("nt-add-icon")) && !state.cur.trashed) {
      iconPick();
      return;
    }
    if (t.parentNode.classList.contains("nt-icons")) {
      state.cur.icon = t.classList.contains("nt-icon-none") ? "" : t.textContent;
      flush();
      save().then(renderPage);
      return;
    }
    var a = t.dataset.a;
    if (a === "save") {
      saveNow();
    } else if (a === "more") {
      pop.hidden = !pop.hidden;
    } else if (a === "pin") {
      state.cur.pinned = !state.cur.pinned;
      t.innerHTML = state.cur.pinned ? STAR_ON : STAR;
      t.classList.toggle("on", state.cur.pinned);
      t.setAttribute("aria-pressed", String(state.cur.pinned));
      save({ pinned: state.cur.pinned });
    } else if (a === "trash") {
      setTrashed(state.cur.id, new Date().toISOString().slice(0, 19));
    } else if (a === "restore") {
      state.trash = false;
      setTrashed(state.cur.id, false);
    } else if (a === "purge") {
      purgeNote(state.cur.id);
    } else if (a === "md") {
      copyMarkdown();
    }
  });
  function copyMarkdown() {
    var md = toMarkdown(main.querySelector(".nt-title").textContent, body);
    (navigator.clipboard ? navigator.clipboard.writeText(md) : Promise.reject()).then(function () {
      toast("마크다운으로 복사했어요.");
    }).catch(function () {
      prompt("복사하세요", md);
    });
  }
  function toMarkdown(title, root) {
    var out = ["# " + (title || "제목 없음"), ""];
    function inline(el) {
      var s = "";
      el.childNodes.forEach(function (c) {
        if (c.nodeType === 3) s += c.textContent;
        else if (/^(B|STRONG)$/.test(c.nodeName)) s += "**" + inline(c) + "**";
        else if (/^(I|EM)$/.test(c.nodeName)) s += "*" + inline(c) + "*";
        else if (c.nodeName === "CODE") s += "`" + c.textContent + "`";
        else if (c.nodeName === "A") s += "[" + inline(c) + "](" + c.getAttribute("href") + ")";
        else if (c.nodeName === "IMG") s += /^data:/.test(c.getAttribute("src")) ? "![그림]" : "![](" + new URL(c.getAttribute("src"), location.href).href + ")";
        else if (c.nodeName === "BR") s += "\n";
        else if (!/^(UL|OL)$/.test(c.nodeName)) s += inline(c);
      });
      return s;
    }
    function list(l, depth) {
      var i = 1;
      Array.prototype.forEach.call(l.children, function (li) {
        var mark = l.nodeName === "OL" ? i++ + ". " : l.classList.contains("todo") ? (li.hasAttribute("data-done") ? "- [x] " : "- [ ] ") : "- ";
        out.push("  ".repeat(depth) + mark + inline(li).trim());
        Array.prototype.forEach.call(li.children, function (c) {
          if (/^(UL|OL)$/.test(c.nodeName)) list(c, depth + 1);
        });
      });
    }
    Array.prototype.forEach.call(root.children, function (b) {
      var n = b.nodeName;
      if (/^H[123]$/.test(n)) out.push("#".repeat(+n[1] + 1) + " " + inline(b));
      else if (n === "UL" || n === "OL") list(b, 0);
      else if (n === "BLOCKQUOTE") out.push("> " + inline(b));
      else if (n === "PRE") out.push("```\n" + b.textContent + "\n```");
      else if (n === "HR") out.push("---");
      else out.push(inline(b));
      out.push("");
    });
    return out.join("\n").replace(/\n{3,}/g, "\n\n");
  }
  // 휴지통이 아닌 모든 페이지를 하나의 .md 파일로(백업·다른 곳에 옮기기용)
  function exportAll() {
    flush();
    var live = state.list.filter(function (n) { return !n.trashed; });
    live.sort(function (a, b) { return (a.created || "").localeCompare(b.created || ""); });
    Promise.all(live.map(function (m) { return store.get(m.id); })).then(function (notes) {
      var parts = notes.map(function (n) {
        var box = document.createElement("div");
        box.innerHTML = clean(n.html || "");
        return toMarkdown((n.icon ? n.icon + " " : "") + (n.title || "제목 없음"), box).replace(/^# (.*)\n/, "# $1\n\n_" + (n.created || "").slice(0, 10) + "_\n");
      });
      var blob = new Blob([parts.join("\n\n---\n\n")], { type: "text/markdown;charset=utf-8" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "연구노트-" + today() + ".md";
      document.body.appendChild(a);
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      toast(notes.length + "개 페이지를 내보냈어요.");
    }).catch(function () {
      toast("내보내지 못했어요.");
    });
  }

  side.addEventListener("click", function (e) {
    var act = e.target.closest(".nt-act");
    if (act) {
      e.preventDefault();
      var aid = act.closest(".nt-item").getAttribute("data-id"), k0 = act.getAttribute("data-act");
      if (k0 === "trash") setTrashed(aid, new Date().toISOString().slice(0, 19));
      else if (k0 === "restore") setTrashed(aid, false);
      else purgeNote(aid);
      return;
    }
    var t = e.target.closest("button, a");
    if (!t) return;
    if (t.classList.contains("nt-new") || t.classList.contains("nt-add")) {
      e.preventDefault();
      newPage();
    } else if (t.classList.contains("nt-apps")) {
      var ap = side.querySelector(".nt-apps-pop");
      ap.hidden = !ap.hidden;
      side.querySelector(".nt-keys").hidden = true;
      t.setAttribute("aria-expanded", String(!ap.hidden));
      return;
    } else if (t.classList.contains("nt-keys-btn")) {
      var k = side.querySelector(".nt-keys");
      k.hidden = !k.hidden;
      return;
    } else if (t.classList.contains("nt-export")) {
      closeApps();
      exportAll();
    } else if (t.classList.contains("nt-trash-btn")) {
      closeApps();
      state.trash = !state.trash;
      renderList();
    } else if (t.classList.contains("nt-back-list")) {
      state.trash = false;
      renderList();
    } else if (t.classList.contains("nt-item")) {
      closeSide();
    }
  });
  app.querySelector(".nt-scrim").addEventListener("click", closeSide);
  function closeApps() {
    var ap = side.querySelector(".nt-apps-pop");
    ap.hidden = true;
    side.querySelector(".nt-apps").setAttribute("aria-expanded", "false");
  }
  document.addEventListener("mousedown", function (e) {
    if (!e.target.closest(".nt-side-foot")) closeApps();
  });
  // 왼쪽 목록 접기·펼치기(Claude처럼 버튼, 노션처럼 Ctrl+\). 접은 상태는 이 브라우저에 기억
  function setSideClosed(v) {
    app.classList.toggle("side-closed", v);
    try { localStorage.setItem("study-notes-side", v ? "closed" : "open"); } catch (e) {}
  }
  try { if (localStorage.getItem("study-notes-side") === "closed") app.classList.add("side-closed"); } catch (e) {}
  app.querySelector(".nt-collapse").addEventListener("click", function () {
    if (window.innerWidth < 768) closeSide();
    else setSideClosed(true);
  });
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "\\") {
      e.preventDefault();
      if (window.innerWidth < 768) app.classList.toggle("side-open");
      else setSideClosed(!app.classList.contains("side-closed"));
    }
  });
  qEl.addEventListener("input", function () {
    state.q = qEl.value.trim();
    renderList();
  });
  window.addEventListener("hashchange", function () {
    var id = location.hash.slice(1);
    if (/^n[a-z0-9]{6,24}$/.test(id) && (!state.cur || state.cur.id !== id)) open(id);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      iconPick(false);
      closeApps();
    }
    // Ctrl+Alt+N 새 페이지 (노션과 같은 단축키)
    if ((e.ctrlKey || e.metaKey) && e.altKey && (e.key === "n" || e.key === "N")) {
      e.preventDefault();
      newPage();
    }
  });

  // ---------- 시작 ----------
  function start() {
    var id = location.hash.slice(1);
    var live = state.list.filter(function (n) { return !n.trashed; });
    if (/^n[a-z0-9]{6,24}$/.test(id)) open(id);
    else if (live.length) {
      live.sort(function (a, b) { return (b.updated || "").localeCompare(a.updated || ""); });
      location.hash = live[0].id;
    } else newPage();
  }
  detect().then(function () {
    banner();
    var moved = remote && window.indexedDB ? migrate().catch(function () { return 0; }) : Promise.resolve(0);
    return moved.then(function (k) {
      if (k) toast("브라우저에 있던 노트 " + k + "개를 사이트 폴더로 옮겼어요.");
      return loadList();
    });
  }).then(start).catch(function () {
    main.innerHTML = '<div class="nt-empty"><div class="nt-empty-ico">⚠️</div><h2>노트를 열지 못했어요</h2><p>이 브라우저가 저장소를 막고 있어요. 시크릿 창이 아닌 보통 창에서 열어 주세요.</p></div>';
  });
  watchServer();
})();
