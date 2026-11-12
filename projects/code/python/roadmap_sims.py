"""연구 로드맵(roadmap.qmd)의 설명용 모의실험. 2026-11-07 (11-08 rank 기준, 11-10 그림 전면 개편·검산 항목 추가).

모두 '모의 데이터'다. 소자 모형은 사이트의 다른 그림과 같은 누설 적분(leaky integrator) 노드이며
실제 이온 소자의 식이 아니다. 소재 가설의 증거로 쓰지 않고, "왜 이런 측정이 필요한가"를 보이는 데만 쓴다.

사용법 (study 폴더에서):  python tools/roadmap_sims.py [출력 폴더]
결과: <출력 폴더>/sim*.png, sims.json (본문·캡션에 적는 숫자는 모두 이 JSON에서 가져온다)
      출력 폴더 기본값: assets/img/roadmap (study 폴더 안에서 실행할 때)

모형과 규약:
  노드 하나: x[k+1] = a·x[k] + (1−a)·u[k],  a = exp(−Δt/τ)  (Δt = 입력 한 칸)
  비선형(sim3만): x[k+1] = tanh(g·(a·x[k] + (1−a)·u[k])) / tanh(g)   (g = 이득, 상태에 걸리는 포화)
  읽기: 마지막 칸의 상태 + 측정 잡음 N(0, σ²)
  readout: 5겹 cross-validation. 겹마다 학습 쪽으로만 표준화, ridge 선형 분류(λ = 1 고정, 탐색 없음).
           점수는 held-out balanced accuracy. 반복 seed 5개의 평균 ± 표준편차를 JSON에 적는다.
  rank: 끝 상태 행렬(열 중심화)의 특이값 중, 같은 모양의 '잡음만' 행렬의 최대 특이값(20회의 95 % 분위)보다
        큰 것의 수. 잡음 draw 10회의 중앙값. (최대 특이값의 5 % 같은 임의 비율 대신 잡음 기준을 쓴다)
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
for cand in (HERE.parent / "projects" / "code" / "python", HERE):
    if (cand / "common.py").exists():
        sys.path.insert(0, str(cand))
        break
from common import korean_plot  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else (HERE.parent / "assets" / "img" / "roadmap" if (HERE.parent / "assets").exists() else HERE / "runs" / "roadmap")
OUT.mkdir(parents=True, exist_ok=True)
plt = korean_plot()
plt.rcParams.update({"font.size": 11.5, "axes.titlesize": 12, "axes.labelsize": 11.5, "legend.fontsize": 10.5,
                     "xtick.labelsize": 10.5, "ytick.labelsize": 10.5, "lines.linewidth": 2.2})
INK = "#1d1d1f"
ACC = "balanced accuracy (시험 데이터)"
A_C, B_C, NOW, HYP, MUTED = "#0e8a83", "#c2682b", "#2b59c3", "#7a3f97", "#525b68"
NUMS = {}
SEEDS = [0, 1, 2, 3, 4]


def panel(ax, s):
    """논문 figure처럼 패널 글자를 축 왼쪽 위 바깥에 둔다."""
    ax.text(-0.16, 1.07, s, transform=ax.transAxes, fontsize=13, fontweight="bold", va="bottom", ha="left")


def fig2(w=8.0, h=3.4, **kw):
    fig, ax = plt.subplots(1, 2, figsize=(w, h), **kw)
    fig.subplots_adjust(left=0.1, right=0.98, bottom=0.17, top=0.86, wspace=0.42)
    return fig, ax


# ------------------------------------------------------------------ 공통
def run_nodes(U, taus, gain=None, dt=1.0):
    taus = np.atleast_1d(np.asarray(taus, float))
    a = np.exp(-dt / taus)
    n, T = U.shape
    X = np.zeros((n, T, len(taus)))
    x = np.zeros((n, len(taus)))
    for k in range(T):
        u = U[:, k][:, None]
        if gain is None:
            x = a * x + (1 - a) * u
        else:
            x = np.tanh(gain * (a * x + (1 - a) * u)) / np.tanh(gain)
        X[:, k, :] = x
    return X


def cv_score(F, y, noise, seed=0, lam=1.0, folds=5):
    rng = np.random.default_rng(seed)
    F = F + rng.normal(0, noise, F.shape)
    n = len(y)
    idx = rng.permutation(n)
    classes = np.unique(y)
    scores = []
    for f in range(folds):
        te = idx[f::folds]
        tr = np.setdiff1d(idx, te)
        mu, sd = F[tr].mean(0), F[tr].std(0) + 1e-9
        Xtr, Xte = (F[tr] - mu) / sd, (F[te] - mu) / sd
        Xtr = np.hstack([Xtr, np.ones((len(tr), 1))])
        Xte = np.hstack([Xte, np.ones((len(te), 1))])
        Y = (y[tr][:, None] == classes[None, :]).astype(float)
        W = np.linalg.solve(Xtr.T @ Xtr + lam * np.eye(Xtr.shape[1]), Xtr.T @ Y)
        pred = classes[np.argmax(Xte @ W, 1)]
        accs = [np.mean(pred[y[te] == c] == c) for c in classes if np.any(y[te] == c)]
        scores.append(np.mean(accs))
    return float(np.mean(scores))


def cv_stats(F, y, noise):
    v = [cv_score(F, y, noise, seed=s) for s in SEEDS]
    return float(np.mean(v)), float(np.std(v))


def noisy_rank(F, noise, seed=0, draws=10, null=20):
    """잡음 기준 rank: 잡음만으로 만든 같은 모양 행렬의 최대 특이값(95 % 분위)보다 큰 특이값의 수. draws회 중앙값."""
    rng = np.random.default_rng(seed)
    S, N = F.shape
    null_max = np.percentile([np.linalg.svd(rng.normal(0, noise, (S, N)) - 0, compute_uv=False)[0] for _ in range(null)], 95)
    rs = []
    for _ in range(draws):
        G = F + rng.normal(0, noise, F.shape)
        G = G - G.mean(0)
        s = np.linalg.svd(G, compute_uv=False)
        rs.append(int(np.sum(s > null_max)))
    return int(np.median(rs)), float(null_max)


# ------------------------------------------------------------------ 모의실험 1: τ가 과제의 간격에 맞아야 한다
def sim1():
    rng = np.random.default_rng(1)
    n, T = 240, 8
    U = np.full((n, T), 0.1)
    y = np.arange(n) % 2
    rng.shuffle(y)
    for i in range(n):
        lo = 0 if y[i] == 0 else 2
        U[i, lo + rng.choice(4, 3, replace=False)] = 1.0
    U += rng.normal(0, 0.02, U.shape)
    taus = np.logspace(-0.7, 1.7, 25)
    noises = [0.003, 0.01, 0.03]
    res = {nz: [cv_stats(run_nodes(U, [t])[:, -1, :], y, nz) for t in taus] for nz in noises}
    diff = [abs(run_nodes(U, [t])[:, -1, 0][y == 0].mean() - run_nodes(U, [t])[:, -1, 0][y == 1].mean()) for t in taus]
    fig = plt.figure(figsize=(8.0, 8.4))
    gs = fig.add_gridspec(3, 6, height_ratios=[0.62, 0.8, 1.2], hspace=0.95, wspace=1.4, left=0.1, right=0.98, top=0.95, bottom=0.075)
    ex = {"펄스 3개가 앞쪽 (칸 0–3)": [0, 1, 3], "펄스 3개가 가운데 (칸 2–5)": [2, 4, 5]}
    # (a) 실험 구성: 두 종류의 입력과 읽는 칸
    for j, ((lab, idx), c) in enumerate(zip(ex.items(), (A_C, B_C))):
        a = fig.add_subplot(gs[0, 3 * j:3 * j + 3])
        u = np.full(T, 0.1)
        u[idx] = 1.0
        a.bar(range(T), u, color=[c if k in idx else "#c9ced6" for k in range(T)], width=0.72)
        a.axvline(T - 1, color=NOW, lw=1.2, ls=":")
        a.text(T - 1.15, 1.2, "여기서 한 번 읽음", color=NOW, fontsize=10, ha="right", va="center")
        a.set_ylim(0, 1.42)
        a.set_xlim(-0.7, T - 0.3)
        a.set_yticks([0, 1])
        a.set_xticks(range(T))
        a.set_xlabel("칸 n (한 칸 = Δt)")
        a.set_title("입력 종류 " + "AB"[j] + ": " + lab, fontsize=11, color=c)
        if j == 0:
            a.set_ylabel("입력 u")
            panel(a, "(a)")
    # (b) 같은 두 입력이 남기는 state
    for j, (t, name) in enumerate(((0.3, "τ/Δt = 0.3 (너무 짧음)"), (3.0, "τ/Δt = 3 (알맞음)"), (30.0, "τ/Δt = 30 (너무 김)"))):
        a = fig.add_subplot(gs[1, 2 * j:2 * j + 2])
        ends = []
        for (lab, idx), c in zip(ex.items(), (A_C, B_C)):
            u = np.full((1, T), 0.1)
            u[0, idx] = 1.0
            x = run_nodes(u, [t])[0, :, 0]
            a.plot(range(T), x, "o-", color=c, ms=3.5)
            ends.append(x[-1])
        a.axvline(T - 1, color=NOW, lw=1, ls=":")
        a.set_title(name + chr(10) + f"읽는 칸에서의 차이 {abs(ends[0] - ends[1]):.3f}", fontsize=10.5, linespacing=1.35)
        a.set_xticks([0, 2, 4, 6])
        a.set_xlabel("칸 n")
        if j == 0:
            a.set_ylabel("state x")
            a.text(-0.38, 1.2, "(b)", transform=a.transAxes, fontsize=13, fontweight="bold", va="bottom", ha="left")
    a0 = fig.add_subplot(gs[2, 0:3])
    a1 = fig.add_subplot(gs[2, 3:6])
    a0.plot(taus, diff, color=INK)
    a0.set_xscale("log")
    a0.set_xlabel("τ/Δt")
    a0.set_ylabel("읽은 값의 차이 (A 평균 − B 평균)")
    a0.set_title("A와 B가 얼마나 다른 값으로 남았나")
    a0.text(0.56, 0.97, "봉우리: 차이가 가장 큼\n= 구분하기 가장 쉬움", transform=a0.transAxes, fontsize=10, color=A_C, va="top")
    a0.text(0.02, 0.40, "너무 짧음:\n둘 다 사라짐", transform=a0.transAxes, fontsize=9.5, color=MUTED, ha="left")
    a0.text(0.98, 0.40, "너무 김:\n둘 다 쌓임", transform=a0.transAxes, fontsize=9.5, color=MUTED, ha="right")
    panel(a0, "(c)")
    for c, nz in zip([A_C, NOW, B_C], noises):
        m = np.array([r[0] for r in res[nz]])
        s_ = np.array([r[1] for r in res[nz]])
        a1.plot(taus, m, color=c, label=f"σ = {nz}")
        a1.fill_between(taus, m - s_, m + s_, color=c, alpha=0.15, lw=0)
    a1.axhline(0.5, color=MUTED, lw=1, ls="--")
    a1.text(0.75, 0.425, "점선: 우연 0.5", fontsize=10, color=MUTED, ha="left")
    a1.set_xscale("log")
    a1.set_ylim(0.38, 1.04)
    a1.set_xlabel("τ/Δt")
    a1.set_ylabel("balanced accuracy (시험 데이터)")
    a1.set_title("A/B를 맞힌 비율")
    a1.legend(loc="center", bbox_to_anchor=(0.47, 0.42), title="읽을 때 더한 잡음", title_fontsize=10, fontsize=10)
    panel(a1, "(d)")
    fig.savefig(OUT / "sim1-tau-window.png")
    plt.close(fig)
    NUMS["sim1"] = {"taus": [round(t, 3) for t in taus],
                    "acc_mean": {str(nz): [round(r[0], 3) for r in res[nz]] for nz in noises},
                    "acc_sd": {str(nz): [round(r[1], 3) for r in res[nz]] for nz in noises},
                    "best": {str(nz): (round(float(taus[int(np.argmax([r[0] for r in res[nz]]))]), 2), round(max(r[0] for r in res[nz]), 3)) for nz in noises},
                    "at_tau_0p2": {str(nz): f"{res[nz][0][0]:.2f} ± {res[nz][0][1]:.2f}" for nz in noises},
                    "at_tau_50": {str(nz): f"{res[nz][-1][0]:.2f} ± {res[nz][-1][1]:.2f}" for nz in noises},
                    "diff_max_tau": round(float(taus[int(np.argmax(diff))]), 2)}


# ------------------------------------------------------------------ 모의실험 2: 시간척도가 둘이면 τ도 둘
def sim2():
    rng = np.random.default_rng(2)
    n, T = 400, 20
    U = np.full((n, T), 0.05)
    y = np.arange(n) % 4
    rng.shuffle(y)
    for i in range(n):
        short, long_ = y[i] % 2, y[i] // 2
        U[i, 16], U[i, 17] = (1.0, 0.4) if short == 0 else (0.4, 1.0)
        if long_ == 1:
            U[i, 2 + rng.choice(4, 3, replace=False)] = 1.0
        U[i, 8 + rng.choice(6, rng.integers(1, 3), replace=False)] = 0.7
    U += rng.normal(0, 0.02, U.shape)
    noise = 0.01
    taus = np.logspace(-0.3, 1.4, 18)
    single = [cv_stats(run_nodes(U, [t])[:, -1, :], y, noise) for t in taus]
    s_short = [cv_stats(run_nodes(U, [t])[:, -1, :], y % 2, noise) for t in taus]
    s_long = [cv_stats(run_nodes(U, [t])[:, -1, :], y // 2, noise) for t in taus]
    tb = float(taus[int(np.argmax([s[0] for s in single]))])
    sets = {"τ 하나 (가장 좋은 τ)": [tb], "같은 τ 셋": [tb, tb, tb], "τ 셋: 1 · 2 · 4": [1.0, 2.0, 4.0], "τ 셋: 0.7 · 2 · 8": [0.7, 2.0, 8.0]}
    results = {k: cv_stats(run_nodes(U, v)[:, -1, :], y, noise) for k, v in sets.items()}
    sub = {}
    for name, tl in (("τ 하나", [tb]), ("τ 셋 0.7·2·8", [0.7, 2.0, 8.0])):
        F = run_nodes(U, tl)[:, -1, :]
        sub[name] = {"short": cv_stats(F, y % 2, noise), "long": cv_stats(F, y // 2, noise)}
    ratios = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 10.0]
    sweep = {str(r): cv_stats(run_nodes(U, [2.4 / r, 2.4, 2.4 * r])[:, -1, :], y, noise) for r in ratios}
    fig = plt.figure(figsize=(8.0, 6.6))
    gs = fig.add_gridspec(2, 20, height_ratios=[0.66, 1.25], hspace=0.6, wspace=0.42, left=0.1, right=0.98, top=0.93, bottom=0.1)
    a = fig.add_subplot(gs[0, 0:13])
    ue = np.full(T, 0.05)
    ue[[2, 3, 5]] = 1.0
    ue[[9, 12]] = 0.7
    ue[16], ue[17] = 1.0, 0.4
    cols = [MUTED] * T
    for k in (2, 3, 4, 5):
        cols[k] = B_C
    for k in (16, 17):
        cols[k] = A_C
    a.bar(range(T), ue, color=cols, width=0.7)
    a.set_xlim(-0.8, T - 0.2)
    a.set_ylim(0, 1.62)
    a.set_yticks([])
    a.set_xticks([0, 5, 10, 15, 19])
    a.set_xlabel("칸 n (입력 하나의 예)")
    a.spines["left"].set_visible(False)
    a.text(3.5, 1.1, "아까 (칸 2–5):\n활성화 동작이 있었나", color=B_C, ha="center", fontsize=10, linespacing=1.3)
    a.text(10.5, 0.8, "상관없는 움직임", color=MUTED, ha="center", fontsize=10)
    a.text(14.6, 1.1, "방금 (칸 16·17):\n어느 쪽이 셌나", color=A_C, ha="center", fontsize=10, linespacing=1.3)
    a.axvline(19, color=NOW, lw=1, ls=":")
    a.text(18.7, 1.5, "읽기", color=NOW, ha="right", fontsize=10)
    a.set_title("입력 하나와 두 질문", fontsize=11.5)
    a.text(-0.06, 1.07, "(a)", transform=a.transAxes, fontsize=13, fontweight="bold", va="bottom", ha="left")
    at = fig.add_subplot(gs[0, 14:20])
    at.axis("off")
    at.set_xlim(0, 3)
    at.set_ylim(0, 3.3)
    at.set_title("정답 4가지", fontsize=11.5)
    at.text(1.5, 2.72, "앞이 셈", ha="center", fontsize=10, color=A_C)
    at.text(2.5, 2.72, "뒤가 셈", ha="center", fontsize=10, color=A_C)
    at.text(0.92, 1.9, "활성화\n없음", ha="right", va="center", fontsize=10, color=B_C, linespacing=1.2)
    at.text(0.92, 0.9, "활성화\n있음", ha="right", va="center", fontsize=10, color=B_C, linespacing=1.2)
    for r_ in range(2):
        for c_ in range(2):
            at.add_patch(plt.Rectangle((1.04 + c_, 1.44 - r_), 0.92, 0.92, facecolor="#eef0f3", edgecolor="none"))
            at.text(1.5 + c_, 1.9 - r_, f"답 {r_ * 2 + c_ + 1}", ha="center", va="center", fontsize=11.5, fontweight="bold", color=INK)
    a0 = fig.add_subplot(gs[1, 0:8])
    a1 = fig.add_subplot(gs[1, 12:20])
    for vals, c, ls in ((s_short, A_C, "-"), (s_long, B_C, "-")):
        a0.plot(taus, [v[0] for v in vals], color=c, ls=ls, lw=2.2)
    a0.axhline(0.5, color=MUTED, lw=1, ls=":")
    a0.text(taus[-1], 0.44, "찍어서 맞힐 확률 0.5", fontsize=9.5, color=MUTED, ha="right", va="top")
    a0.set_xscale("log")
    a0.set_ylim(0.1, 1.08)
    a0.set_xlabel("소자의 τ (칸 단위, 소자 1개)")
    a0.set_ylabel("질문 하나를 맞힌 비율")
    a0.set_ylim(0.3, 1.08)
    a0.set_title("소자 1개: 한쪽 질문만 맞힌다")
    a0.text(1.5, 0.92, "방금 질문", color=A_C, fontsize=10.5, ha="center", fontweight="bold")
    a0.text(9.5, 1.01, "아까 질문", color=B_C, fontsize=10.5, ha="right", fontweight="bold")
    panel(a0, "(b)")
    names = ["소자 1개\n(가장 좋은 τ)", "소자 3개\nτ가 모두 같음", "소자 3개\nτ = 1 · 2 · 4", "소자 3개\nτ = 0.7 · 2 · 8"]
    keys = list(results)
    vals = [results[k][0] for k in keys]
    errs = [results[k][1] for k in keys]
    a1.barh(range(len(names)), vals, xerr=errs, color=[MUTED, MUTED, A_C, A_C], capsize=3, error_kw={"lw": 1}, height=0.6)
    a1.set_yticks(range(len(names)))
    a1.set_yticklabels(names, fontsize=10)
    a1.invert_yaxis()
    a1.set_xlim(0, 1.0)
    a1.axvline(0.25, color=MUTED, lw=1, ls=":")
    for i, v in enumerate(vals):
        a1.text(v + errs[i] + 0.02, i, f"{v:.2f}", va="center", fontsize=11)
    a1.set_xlabel("두 질문을 모두 맞힌 비율 (찍으면 0.25)")
    a1.set_title("소자를 3개로 늘리면")
    a1.text(-0.5, 1.07, "(c)", transform=a1.transAxes, fontsize=13, fontweight="bold", va="bottom", ha="left")
    fig.savefig(OUT / "sim2-multi-tau.png")
    plt.close(fig)
    NUMS["sim2"] = {"best_single_tau": round(tb, 2), "results": {k: f"{v[0]:.2f} ± {v[1]:.2f}" for k, v in results.items()},
                    "short_long": {k: {kk: f"{vv[0]:.2f} ± {vv[1]:.2f}" for kk, vv in v.items()} for k, v in sub.items()},
                    "spacing_sweep_center_2p4": {k: f"{v[0]:.2f} ± {v[1]:.2f}" for k, v in sweep.items()}}


# ------------------------------------------------------------------ 모의실험 3: 비선형·포화·잡음의 trade-off
def sim3():
    rng = np.random.default_rng(3)
    n = 400
    lv = np.array([0.3, 0.9])
    b1, b2 = rng.integers(0, 2, n), rng.integers(0, 2, n)
    U = np.zeros((n, 4))
    U[:, 1], U[:, 2] = lv[b1], lv[b2]
    U += rng.normal(0, 0.02, U.shape)
    y_xor = (b1 != b2).astype(int)
    y_sum = b1 + b2
    gains = np.logspace(-1, 1.3, 16)
    noises = [0.003, 0.03]
    res = {}
    for nz in noises:
        ax_, as_ = [], []
        for g in gains:
            F = run_nodes(U, [0.8, 3.0], gain=g)[:, 2:, :].reshape(n, -1)
            ax_.append(cv_stats(F, y_xor, nz))
            as_.append(cv_stats(F, y_sum, nz))
        res[nz] = (ax_, as_)
    fig = plt.figure(figsize=(8.0, 3.7))
    gs = fig.add_gridspec(1, 2, wspace=0.4, left=0.06, right=0.98, top=0.87, bottom=0.27)
    a = fig.add_subplot(gs[0, 0])
    a.axis("off")
    a.set_xlim(0, 10)
    a.set_ylim(0, 10)
    a.set_title("두 과제: 펄스 두 개(약/강)를 넣고 묻는다")
    a.text(1.15, 9.0, "펄스 1", fontsize=10.5, color=MUTED, ha="center")
    a.text(3.55, 9.0, "펄스 2", fontsize=10.5, color=MUTED, ha="center")
    a.text(6.2, 9.0, "서로 다른가?\n(XOR)", fontsize=10.5, color=A_C, va="center", ha="center", linespacing=1.2)
    a.text(8.9, 9.0, "강한 펄스 수", fontsize=10.5, color=B_C, ha="center")
    for r, (p1, p2) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
        yy = 6.9 - r * 1.75
        for xx, v in ((0.2, p1), (2.6, p2)):
            a.add_patch(plt.Rectangle((xx, yy - 0.55), 1.9, 1.1, color="#dfe3ea" if v == 0 else "#5a6270", lw=0))
            a.text(xx + 0.95, yy, "약" if v == 0 else "강", ha="center", va="center", fontsize=11, color=INK if v == 0 else "white")
        a.text(6.2, yy, "아니오 (0)" if p1 == p2 else "예 (1)", ha="center", va="center", fontsize=11.5, color=A_C, fontweight="bold")
        a.text(8.9, yy, str(p1 + p2), ha="center", va="center", fontsize=13, color=B_C, fontweight="bold")
    panel(a, "(a)")
    a = fig.add_subplot(gs[0, 1])
    u = np.linspace(0, 1, 100)

    def f(g, v):
        return np.tanh(g * v) / np.tanh(g)

    for g, c in ((0.3, MUTED), (3, NOW), (15, HYP)):
        a.plot(u, f(g, u), color=c, label=f"g = {g}")
    for g, c in ((0.3, MUTED), (15, HYP)):
        for v in (0.3, 0.9):
            a.plot([v, v], [0, f(g, v)], color=c, lw=0.8, ls=":")
            a.plot(v, f(g, v), "o", color=c, ms=5)
    a.text(0.6, 0.13, "g = 15에서는 약과 강의\n응답이 같아진다 (보라 점 둘)", color=HYP, fontsize=10, ha="center", linespacing=1.3)
    a.set_xticks([0, 0.3, 0.9])
    a.set_xticklabels(["0", "약 0.3", "강 0.9"])
    a.set_xlabel("입력 세기 u")
    a.set_ylabel("노드의 응답 (정규화)")
    a.set_title("g = 비선형(포화)의 세기")
    a.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=3, fontsize=10, columnspacing=1.2, handlelength=1.4)
    panel(a, "(b)")
    fig.savefig(OUT / "sim3-nonlinearity.png")
    plt.close(fig)
    fig = plt.figure(figsize=(8.0, 3.7))
    gs = fig.add_gridspec(1, 2, wspace=0.34, left=0.09, right=0.98, top=0.86, bottom=0.2)
    for j, (title, key, chance, lab, col) in enumerate((("'서로 다른가'(XOR): 덧셈만으론 못 푼다", 0, 0.5, "(c)", A_C), ("'강한 펄스의 개수': 포화되면 못 푼다", 1, 1 / 3, "(d)", B_C))):
        a = fig.add_subplot(gs[0, j])
        for nz, ls in zip(noises, ("-", "--")):
            a.plot(gains, [r[0] for r in res[nz][key]], color=col, ls=ls, label=f"σ = {nz}")
        a.axhline(chance, color=MUTED, lw=1, ls=":")
        a.text(gains[0], chance + (0.02 if j == 1 else -0.02), f"점선: 우연 {chance:.2f}", fontsize=10, color=MUTED, ha="left", va="bottom" if j == 1 else "top")
        a.set_xscale("log")
        a.set_ylim(0.2, 1.06)
        a.set_xlabel("g   (← 거의 선형 · 심한 포화 →)")
        a.set_ylabel(ACC)
        a.set_title(title, fontsize=11.5)
        a.legend(loc="center left" if j == 1 else "upper left", fontsize=10, title="읽기 잡음", title_fontsize=10, handlelength=1.6)
        panel(a, lab)
    fig.savefig(OUT / "sim3-results.png")
    plt.close(fig)
    NUMS["sim3"] = {"gains": [round(g, 2) for g in gains], "sat_out": {str(g): [round(float(f(g, 0.3)), 3), round(float(f(g, 0.9)), 3)] for g in (0.3, 3, 15)}}
    for nz in noises:
        xo, sm = res[nz]
        NUMS["sim3"][str(nz)] = {"xor_max": f"{max(r[0] for r in xo):.2f} (g = {gains[int(np.argmax([r[0] for r in xo]))]:.1f})",
                                 "xor_at_g_0p1": f"{xo[0][0]:.2f}", "xor_at_g_20": f"{xo[-1][0]:.2f}",
                                 "sum_at_g_le_2": f"{min(r[0] for r, g in zip(sm, gains) if g <= 2):.2f}",
                                 "sum_at_g_20": f"{sm[-1][0]:.2f}"}


# ------------------------------------------------------------------ 모의실험 4: 노드 수 ≠ 독립 정보량
def sim4():
    rng = np.random.default_rng(4)
    pats = np.array([[int(b) for b in f"{i:04b}"] for i in range(16)], float)
    pats = np.where(pats > 0, 1.0, 0.1)
    U = np.hstack([pats, np.full((16, 1), 0.1)])
    reps = 8
    Urep = np.repeat(U, reps, 0) + rng.normal(0, 0.01, (16 * reps, 5))
    yrep = np.repeat(np.arange(16), reps)
    Ns = [1, 2, 3, 4, 6, 8, 12, 16]
    noise = 0.004
    labs = {"same": "모두 같은 τ (= 2)", "spread": "τ를 0.5–8에 고르게", "spread_var": "고르게 + 무작위 편차 ±25 %"}
    sty = {"same": dict(color=MUTED, marker="o", ls="-"), "spread": dict(color=A_C, marker="o", ls="-", ms=8),
           "spread_var": dict(color=HYP, marker="s", ls="--", mfc="white", ms=5)}
    rank = {k: [] for k in labs}
    exact = {k: [] for k in labs}
    acc = {k: [] for k in labs}
    for N in Ns:
        sets = {"same": np.full(N, 2.0), "spread": np.logspace(np.log10(0.5), np.log10(8), N)}
        sets["spread_var"] = sets["spread"] * (1 + rng.normal(0, 0.25, N)).clip(0.3)
        for k, taus in sets.items():
            F = run_nodes(U, taus)[:, -1, :]
            rank[k].append(noisy_rank(F, noise)[0])
            exact[k].append(int(np.linalg.matrix_rank(F - F.mean(0), tol=1e-9)))
            acc[k].append(cv_stats(run_nodes(Urep, taus)[:, -1, :], yrep, noise))
    F16 = run_nodes(U, np.logspace(np.log10(0.5), np.log10(8), 16))[:, -1, :]
    sv = np.linalg.svd(F16 - F16.mean(0), compute_uv=False)[:5]
    thr = noisy_rank(F16, noise)[1]
    fig, ax = fig2(w=8.0, h=4.0)
    fig.subplots_adjust(bottom=0.34, top=0.88, wspace=0.36)
    for k in labs:
        ax[0].plot(Ns, rank[k], label=labs[k], **sty[k])
    ax[0].axhline(4, color=MUTED, lw=1, ls=":")
    ax[0].text(16, 4.14, "계산상 상한 4 (입력이 4칸)", fontsize=10, color=MUTED, ha="right")
    ax[0].text(16, 2.52, "청록과 보라가 겹침", fontsize=10, color=A_C, ha="right")
    ax[0].set_ylim(0, 5)
    ax[0].set_yticks(range(6))
    ax[0].set_xticks([1, 4, 8, 12, 16])
    ax[0].set_xlabel("노드 수 N")
    ax[0].set_ylabel("잡음보다 큰 방향의 수 (rank)")
    ax[0].set_title("서로 다른 정보의 수")
    panel(ax[0], "(a)")
    for k in labs:
        m = np.array([a[0] for a in acc[k]])
        s_ = np.array([a[1] for a in acc[k]])
        ax[1].errorbar(Ns, m, yerr=s_, capsize=2, label=labs[k], **sty[k])
    ax[1].axhline(1 / 16, color=MUTED, lw=1, ls=":")
    ax[1].text(16, 1 / 16 + 0.1, "우연 1/16", fontsize=10, color=MUTED, ha="right")
    ax[1].set_ylim(0, 1.0)
    ax[1].set_xticks([1, 4, 8, 12, 16])
    ax[1].set_xlabel("노드 수 N")
    ax[1].set_ylabel("16가지 입력을 맞히는 정확도")
    ax[1].set_title("과제 정확도 (막대 = ±1 SD, seed 5)")
    panel(ax[1], "(b)")
    h, l = ax[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, fontsize=10.5, bbox_to_anchor=(0.54, 0.02), columnspacing=1.4)
    fig.savefig(OUT / "sim4-rank-vs-nodes.png")
    plt.close(fig)
    NUMS["sim4"] = {"Ns": Ns, "rank": rank, "exact_rank": exact, "acc": {k: [f"{a[0]:.2f} ± {a[1]:.2f}" for a in v] for k, v in acc.items()},
                    "singular_values_N16_spread": [round(float(v), 4) for v in sv], "noise_threshold_N16": round(thr, 4)}


# ------------------------------------------------------------------ 모의실험 5: 지표 계산 예 (separability·KR·GR)
def sim5():
    rng = np.random.default_rng(5)
    pats = np.array([[int(b) for b in f"{i:04b}"] for i in range(16)], float)
    pats = np.where(pats > 0, 1.0, 0.1)
    U = np.hstack([pats, np.full((16, 1), 0.1)])
    taus = [0.7, 2.0, 6.0]
    F = run_nodes(U, taus)[:, -1, :]
    noise = 0.01
    reps = 10
    Fr = np.repeat(F, reps, 0) + rng.normal(0, noise, (16 * reps, 3))
    lab = np.repeat(np.arange(16), reps)
    D = np.linalg.norm(Fr[:, None, :] - Fr[None, :, :], axis=2)
    iu = np.triu_indices(len(Fr), 1)
    between = D[iu][lab[iu[0]] != lab[iu[1]]]
    within = D[iu][lab[iu[0]] == lab[iu[1]]]
    sep = float(between.mean() / within.mean())
    kr, thr = noisy_rank(F, noise)
    sim_idx = [i for i in range(16) if f"{i:04b}".endswith("11")]
    gr, thr_g = noisy_rank(F[sim_idx], noise)
    kr_same, _ = noisy_rank(run_nodes(U, [2.0, 2.0, 2.0])[:, -1, :], noise)
    sv = np.linalg.svd(F - F.mean(0), compute_uv=False)
    fig = plt.figure(figsize=(8.0, 6.9))
    gs = fig.add_gridspec(2, 2, hspace=0.72, wspace=0.42, left=0.1, right=0.98, top=0.94, bottom=0.11)
    a = fig.add_subplot(gs[0, 0])
    show = {0: MUTED, 6: A_C, 9: B_C, 15: HYP}
    for i in range(16):
        m = lab == i
        a.scatter(Fr[m, 0], Fr[m, 2], s=14, color=show.get(i, "#c9ced6"), zorder=3 if i in show else 1)
    for i, c in show.items():
        a.annotate(f"{i:04b}", (F[i, 0], F[i, 2]), fontsize=11, color=c, fontweight="bold", xytext=((0, -22) if i == 9 else (7, 5)), ha=("center" if i == 9 else "left"), textcoords="offset points")
    a.set_xlabel("노드 1 (τ = 0.7)에서 읽은 상태")
    a.set_ylabel("노드 3 (τ = 6)에서 읽은 상태")
    a.set_xlim(0.05, 0.42)
    a.set_title("입력열 16가지 × 10번 반복")
    panel(a, "(a)")
    a = fig.add_subplot(gs[0, 1])
    a.hist(within, bins=12, color=B_C, alpha=0.9, density=True, label=f"같은 입력을 반복한 쌍 ({len(within)}쌍)")
    a.hist(between, bins=30, color=A_C, alpha=0.75, density=True, label=f"다른 입력끼리의 쌍 ({len(between)}쌍)")
    a.set_yscale("log")
    a.axvline(within.mean(), color=B_C, lw=1.2, ls="--")
    a.axvline(between.mean(), color=A_C, lw=1.2, ls="--")
    top = a.get_ylim()[1]
    a.text(within.mean() + 0.012, top * 0.6, f"평균 {within.mean():.3f}", color=B_C, fontsize=10.5, va="top")
    a.text(between.mean() + 0.012, top * 0.12, f"평균 {between.mean():.3f}", color=A_C, fontsize=10.5, va="top")
    a.set_xlabel("두 측정의 상태 사이 거리")
    a.set_ylabel("쌍의 비율 (밀도, 로그 눈금)")
    a.set_title(f"separability = {between.mean():.3f} ÷ {within.mean():.3f} = {sep:.0f}")
    a.legend(loc="upper center", bbox_to_anchor=(0.5, -0.26), fontsize=10, ncol=1)
    panel(a, "(b)")
    a = fig.add_subplot(gs[1, 0])
    a.bar(range(1, 4), sv, color=[A_C if v > thr else "#c9ced6" for v in sv], width=0.55)
    a.axhline(thr, color=B_C, lw=1.4, ls="--")
    a.text(0.98, 0.93, f"점선: 잡음만으로 생기는 크기 {thr:.3f}", color=B_C, fontsize=10.5, ha="right", transform=a.transAxes)
    a.set_yscale("log")
    a.set_xticks([1, 2, 3])
    a.set_xticklabels(["방향 1", "방향 2", "방향 3"])
    a.set_ylabel("그 방향으로 퍼진 크기 (특이값)")
    a.set_title(f"잡음보다 큰 방향 = {kr}개 → rank {kr}")
    panel(a, "(c)")
    a = fig.add_subplot(gs[1, 1])
    names = ["서로 다른 입력\n16가지 (KR)", "끝 두 칸이 같은\n입력 4가지 (GR)", "같은 τ인 노드\n셋으로 다시 (KR)"]
    vals = [kr, gr, kr_same]
    a.bar(range(3), vals, color=[A_C, NOW, MUTED], width=0.55)
    a.set_xticks(range(3))
    a.set_xticklabels(names, fontsize=10)
    a.set_ylim(0, 3.6)
    a.set_yticks([0, 1, 2, 3])
    a.set_ylabel("rank")
    for i, v in enumerate(vals):
        a.text(i, v + 0.1, str(v), ha="center", fontsize=12, fontweight="bold")
    a.set_title("같은 방법으로 센 세 가지 rank")
    panel(a, "(d)")
    fig.savefig(OUT / "sim5-metrics-example.png")
    plt.close(fig)
    NUMS["sim5"] = {"separability": round(sep, 1), "within_mean": round(float(within.mean()), 3), "between_mean": round(float(between.mean()), 3),
                    "pairs_within": int(len(within)), "pairs_between": int(len(between)),
                    "KR": kr, "GR": gr, "KR_same_tau": kr_same, "noise_threshold_sv": round(thr, 4), "singular_values": [round(float(v), 4) for v in sv]}


if __name__ == "__main__":
    for f in (sim1, sim2, sim3, sim4, sim5):
        f()
        print("done", f.__name__)
    (OUT / "sims.json").write_text(json.dumps(NUMS, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", OUT / "sims.json")
