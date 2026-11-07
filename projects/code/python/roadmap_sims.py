"""연구 로드맵(roadmap.qmd)의 설명용 모의실험. 2026-11-07 (11-08 그림·불확실성·rank 기준 수정).

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
plt.rcParams.update({"font.size": 10.5, "axes.titlesize": 11, "axes.labelsize": 10.5, "legend.fontsize": 9,
                     "xtick.labelsize": 9.5, "ytick.labelsize": 9.5})
A_C, B_C, NOW, HYP, MUTED = "#0e8a83", "#c2682b", "#2b59c3", "#7a3f97", "#525b68"
NUMS = {}
SEEDS = [0, 1, 2, 3, 4]


def panel(ax, s):
    """논문 figure처럼 패널 글자를 축 왼쪽 위 바깥에 둔다."""
    ax.text(-0.17, 1.08, s, transform=ax.transAxes, fontsize=12, fontweight="bold", va="bottom", ha="left")


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
    fig, ax = fig2()
    ax[0].plot(taus, diff, color=NOW, lw=2)
    ax[0].set_xscale("log")
    ax[0].set_xlabel("τ / Δt")
    ax[0].set_ylabel("끝 상태의 class 평균 차이")
    ax[0].set_title("차이는 τ ≈ 기억할 간격에서 최대")
    for nz in noises:
        ax[0].axhline(2 * nz, color=MUTED, lw=0.8, ls=":")
    ax[0].text(taus[0], 2 * 0.03 + 0.004, "점선: 잡음 σ의 2배 (0.003 · 0.01 · 0.03)", fontsize=8.5, color=MUTED)
    panel(ax[0], "(a)")
    for c, nz in zip([A_C, NOW, B_C], noises):
        m = np.array([r[0] for r in res[nz]])
        s = np.array([r[1] for r in res[nz]])
        ax[1].plot(taus, m, color=c, lw=2, label=f"σ = {nz}")
        ax[1].fill_between(taus, m - s, m + s, color=c, alpha=0.15, lw=0)
    ax[1].axhline(0.5, color=MUTED, lw=0.8, ls="--", label="우연 수준 0.5")
    ax[1].axvspan(2, 6, color="#fff3cf", zorder=0)
    ax[1].text(3.4, 0.405, "기억할 간격 2–6칸", fontsize=8.5, color="#8a6a10", ha="center")
    ax[1].set_xscale("log")
    ax[1].set_ylim(0.38, 1.04)
    ax[1].set_xlabel("τ / Δt")
    ax[1].set_ylabel("balanced accuracy")
    ax[1].set_title("짧아도 길어도 못 가른다 (띠 = ±1 SD, seed 5)")
    ax[1].legend(loc="upper left", title="측정 잡음", title_fontsize=9)
    panel(ax[1], "(b)")
    fig.savefig(OUT / "sim1-tau-window.png")
    plt.close(fig)
    NUMS["sim1"] = {"taus": [round(t, 3) for t in taus],
                    "acc_mean": {str(nz): [round(r[0], 3) for r in res[nz]] for nz in noises},
                    "acc_sd": {str(nz): [round(r[1], 3) for r in res[nz]] for nz in noises},
                    "best": {str(nz): (round(float(taus[int(np.argmax([r[0] for r in res[nz]]))]), 2), round(max(r[0] for r in res[nz]), 3)) for nz in noises},
                    "at_tau_0p2": {str(nz): f"{res[nz][0][0]:.2f} ± {res[nz][0][1]:.2f}" for nz in noises},
                    "at_tau_50": {str(nz): f"{res[nz][-1][0]:.2f} ± {res[nz][-1][1]:.2f}" for nz in noises}}


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
    tb = float(taus[int(np.argmax([s[0] for s in single]))])
    sets = {"τ 하나 (최적 τ)": [tb], "같은 τ 셋 (중복)": [tb, tb, tb], "τ 셋: 0.7·2·8": [0.7, 2.0, 8.0], "τ 셋: 1·2·4": [1.0, 2.0, 4.0]}
    results = {k: cv_stats(run_nodes(U, v)[:, -1, :], y, noise) for k, v in sets.items()}
    sub = {}
    for name, tl in (("τ 하나", [tb]), ("τ 셋 0.7·2·8", [0.7, 2.0, 8.0])):
        F = run_nodes(U, tl)[:, -1, :]
        sub[name] = {"short": cv_stats(F, y % 2, noise), "long": cv_stats(F, y // 2, noise)}
    fig, ax = fig2(w=8.0, h=3.4, gridspec_kw={"width_ratios": [1.05, 1]})
    m = np.array([s[0] for s in single])
    sd = np.array([s[1] for s in single])
    ax[0].plot(taus, m, color=NOW, lw=2)
    ax[0].fill_between(taus, m - sd, m + sd, color=NOW, alpha=0.15, lw=0)
    ax[0].axhline(0.25, color=MUTED, lw=0.8, ls="--")
    ax[0].text(taus[-1], 0.265, "우연 0.25 (4 class)", fontsize=8.5, color=MUTED, ha="right")
    ax[0].set_xscale("log")
    ax[0].set_xlabel("τ / Δt (노드 하나)")
    ax[0].set_ylabel("balanced accuracy")
    ax[0].set_ylim(0.15, 1.04)
    ax[0].set_title("τ 하나: 어느 τ도 두 정보를 다 못 잡는다")
    panel(ax[0], "(a)")
    names = list(results)
    vals = [results[k][0] for k in names]
    errs = [results[k][1] for k in names]
    ax[1].barh(range(len(names)), vals, xerr=errs, color=[NOW, MUTED, A_C, A_C], capsize=3, error_kw={"lw": 1})
    ax[1].set_yticks(range(len(names)))
    ax[1].set_yticklabels(names)
    ax[1].invert_yaxis()
    ax[1].set_xlim(0, 1.0)
    ax[1].axvline(0.25, color=MUTED, lw=0.8, ls="--")
    for i, v in enumerate(vals):
        ax[1].text(min(v + errs[i] + 0.02, 0.86), i, f"{v:.2f}", va="center", fontsize=9.5)
    ax[1].set_xlabel("balanced accuracy (끝만 읽기)")
    ax[1].set_title("τ가 다른 셋이 가장 높다")
    panel(ax[1], "(b)")
    fig.savefig(OUT / "sim2-multi-tau.png")
    plt.close(fig)
    NUMS["sim2"] = {"best_single_tau": round(tb, 2), "results": {k: f"{v[0]:.2f} ± {v[1]:.2f}" for k, v in results.items()},
                    "short_long": {k: {kk: f"{vv[0]:.2f} ± {vv[1]:.2f}" for kk, vv in v.items()} for k, v in sub.items()}}


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
    fig, ax = fig2(w=8.0, h=3.6)
    fig.subplots_adjust(bottom=0.3)
    for c, nz in zip([A_C, B_C], noises):
        ax[0].plot(gains, [r[0] for r in res[nz][0]], color=c, lw=2, label=f"XOR(순서·조합), σ = {nz}")
        ax[0].plot(gains, [r[0] for r in res[nz][1]], color=c, lw=2, ls="--", label=f"합의 크기 3수준, σ = {nz}")
    ax[0].set_xscale("log")
    ax[0].set_xlabel("비선형 이득 g (작음 = 거의 선형, 큼 = 포화)")
    ax[0].set_ylabel("balanced accuracy")
    ax[0].set_ylim(0.2, 1.04)
    ax[0].set_title("XOR엔 비선형이 필요, 크기는 포화에서 사라진다")
    ax[0].legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=2, frameon=False)
    panel(ax[0], "(a)")
    u = np.linspace(0, 1, 100)
    for g, c in ((0.3, A_C), (3, NOW), (15, B_C)):
        ax[1].plot(u, np.tanh(g * u) / np.tanh(g), color=c, lw=2, label=f"g = {g}")
    ax[1].scatter([0.3, 0.9], [0, 0], color=MUTED, zorder=3)
    ax[1].text(0.3, 0.06, "약", ha="center", fontsize=9, color=MUTED)
    ax[1].text(0.9, 0.06, "강", ha="center", fontsize=9, color=MUTED)
    ax[1].set_xlabel("입력 u (점: 과제의 '약'·'강')")
    ax[1].set_ylabel("노드 응답 f(u)")
    ax[1].set_title("포화 곡선")
    ax[1].legend(loc="center right", bbox_to_anchor=(1.0, 0.5))
    panel(ax[1], "(b)")
    fig.savefig(OUT / "sim3-nonlinearity.png")
    plt.close(fig)
    NUMS["sim3"] = {"gains": [round(g, 2) for g in gains]}
    for nz in noises:
        xo, sm = res[nz]
        NUMS["sim3"][str(nz)] = {"xor_max": f"{max(r[0] for r in xo):.2f} (g = {gains[int(np.argmax([r[0] for r in xo]))]:.1f})",
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
    labs = {"same": "모두 같은 τ (= 2)", "spread": "τ 0.5–8 고르게", "spread_var": "고르게 + 소자 편차 ±25 %"}
    cols = {"same": MUTED, "spread": A_C, "spread_var": HYP}
    rank = {k: [] for k in labs}
    acc = {k: [] for k in labs}
    for N in Ns:
        sets = {"same": np.full(N, 2.0), "spread": np.logspace(np.log10(0.5), np.log10(8), N)}
        sets["spread_var"] = sets["spread"] * (1 + rng.normal(0, 0.25, N)).clip(0.3)
        for k, taus in sets.items():
            rank[k].append(noisy_rank(run_nodes(U, taus)[:, -1, :], noise)[0])
            acc[k].append(cv_stats(run_nodes(Urep, taus)[:, -1, :], yrep, noise))
    fig, ax = fig2()
    for k in labs:
        ax[0].plot(Ns, rank[k], "o-", color=cols[k], lw=2, label=labs[k])
    ax[0].plot(Ns, Ns, color="#c6cedb", lw=1, ls=":")
    ax[0].text(Ns[-1], Ns[-1] - 1.6, "rank = N", fontsize=8.5, color=MUTED, ha="right")
    ax[0].set_xlabel("노드 수 N")
    ax[0].set_ylabel("잡음 기준 rank")
    ax[0].set_title("노드를 늘려도 rank는 몇에서 멈춘다")
    ax[0].legend(loc="upper left")
    panel(ax[0], "(a)")
    for k in labs:
        m = np.array([a[0] for a in acc[k]])
        s = np.array([a[1] for a in acc[k]])
        ax[1].errorbar(Ns, m, yerr=s, fmt="o-", color=cols[k], lw=2, capsize=2, label=labs[k])
    ax[1].axhline(1 / 16, color=MUTED, lw=0.8, ls="--", label="우연 수준 1/16")
    ax[1].legend(loc="upper left", bbox_to_anchor=(0.0, 1.0))
    ax[1].set_ylim(0, 1.0)
    ax[1].set_xlabel("노드 수 N")
    ax[1].set_ylabel("16-pattern balanced accuracy")
    ax[1].set_title("정확도도 천천히 포화한다 (±1 SD)")
    panel(ax[1], "(b)")
    fig.savefig(OUT / "sim4-rank-vs-nodes.png")
    plt.close(fig)
    NUMS["sim4"] = {"Ns": Ns, "rank": rank, "acc": {k: [f"{a[0]:.2f} ± {a[1]:.2f}" for a in v] for k, v in acc.items()}}


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
    gr, _ = noisy_rank(F[sim_idx], noise)
    kr_same, _ = noisy_rank(run_nodes(U, [2.0, 2.0, 2.0])[:, -1, :], noise)
    fig, ax = plt.subplots(1, 3, figsize=(8.0, 3.3), gridspec_kw={"width_ratios": [1.15, 1, 0.8]})
    fig.subplots_adjust(left=0.08, right=0.99, bottom=0.2, top=0.85, wspace=0.5)
    ax[0].scatter(Fr[:, 0], Fr[:, 2], c=lab, cmap="tab20", s=10)
    for i in range(16):
        ax[0].annotate(f"{i:04b}", (F[i, 0], F[i, 2]), fontsize=6.5, color="#2b313a", xytext=(3, -2), textcoords="offset points")
    ax[0].set_xlabel("노드 1 (τ = 0.7) 끝 상태")
    ax[0].set_ylabel("노드 3 (τ = 6) 끝 상태")
    ax[0].set_xlim(0.05, 0.4)
    ax[0].set_title("16가지 입력열의 끝 상태")
    panel(ax[0], "(a)")
    ax[1].hist(between, bins=25, color=A_C, alpha=0.8, label="다른 입력끼리")
    ax[1].hist(within, bins=10, color=B_C, alpha=0.9, label="같은 입력 반복끼리")
    ax[1].set_xlabel("끝 상태 사이 거리")
    ax[1].set_ylabel("쌍의 수")
    ax[1].set_title(f"separability = {sep:.0f}")
    ax[1].set_ylim(0, ax[1].get_ylim()[1] * 1.4)
    ax[1].legend(loc="upper right")
    panel(ax[1], "(b)")
    names = ["KR", "GR", "KR\n(같은 τ)"]
    vals = [kr, gr, kr_same]
    ax[2].bar(range(3), vals, color=[A_C, B_C, MUTED], width=0.6)
    ax[2].set_xticks(range(3))
    ax[2].set_xticklabels(names)
    ax[2].set_ylim(0, 3.6)
    ax[2].set_yticks([0, 1, 2, 3])
    ax[2].set_ylabel("잡음 기준 rank")
    for i, v in enumerate(vals):
        ax[2].text(i, v + 0.08, str(v), ha="center", fontsize=9.5)
    ax[2].set_title("상태 다양성")
    panel(ax[2], "(c)")
    fig.savefig(OUT / "sim5-metrics-example.png")
    plt.close(fig)
    NUMS["sim5"] = {"separability": round(sep, 1), "within_mean": round(float(within.mean()), 3), "between_mean": round(float(between.mean()), 3),
                    "KR": kr, "GR": gr, "KR_same_tau": kr_same, "noise_threshold_sv": round(thr, 4)}


if __name__ == "__main__":
    for f in (sim1, sim2, sim3, sim4, sim5):
        f()
        print("done", f.__name__)
    (OUT / "sims.json").write_text(json.dumps(NUMS, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", OUT / "sims.json")
