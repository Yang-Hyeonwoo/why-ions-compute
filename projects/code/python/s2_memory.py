"""S2: 같은 시간 패턴을 기억 없는 모델·R–C 하나·작은 reservoir에 넣고, '끝만 읽어서' 두 패턴을 가를 수 있는지 비교한다.

장비가 필요 없다. 과제는 A2와 같은 모양이다: 12칸 입력 중 높은 값 3개가 앞쪽(0–3칸)이면 0, 뒤쪽(4–7칸)이면 1.
8–11칸은 두 패턴 모두 낮은 값(0.1)이고, 시행마다 같은 분포의 작은 잡음(표준편차 0.03)만 더해진다.
배열 값이 똑같지는 않지만 패턴에 따른 차이가 없으므로, 8–11칸의 상태만 읽어 맞힌다면 그 상태에 앞 입력의 흔적이 남았다는 뜻이다.

사용법:
  python s2_memory.py runs/s2
  python s2_memory.py runs/s2 --taus 0.3,1,3,10,100 --n 200 --noise 0.01 --seed 1

결과 (출력 폴더):
  s2_table.csv   모델·설정마다 끝만 읽기 균형 정확도(5겹 교차검증 평균 ± 표준편차)와 라벨 섞기 확인 값
  s2_inputs.png  두 패턴의 입력 예 한 개씩 (읽는 칸 표시)
  s2_memory.png  (a) R–C의 τ에 따른 정확도 / (b) τ가 다른 R–C 셋의 상태 곡선(두 패턴 평균)

모형의 가정:
  - R–C 하나: x[k] = a·x[k−1] + (1−a)·u[k], a = exp(−1/τ) (한 칸 = 시간 1, τ도 칸 단위).
  - 작은 reservoir: 노드 30개, tanh, 스펙트럼 반경 0.9, leak 0.3, 입력·연결 가중치 무작위(seed 고정).
  - 읽는 상태에 측정 잡음(표준편차 --noise)을 더한다. 잡음이 없으면 아주 작은 차이도 구별되어 비교가 무의미해진다.
  - readout: 5겹 교차검증, 겹마다 학습 쪽으로만 표준화, ridge(λ=1) 선형 분류.
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np


def make_task(n, seed):
    rng = np.random.default_rng(seed)
    U = np.full((n, 12), 0.1)
    y = np.arange(n) % 2
    rng.shuffle(y)
    for i in range(n):
        lo = 0 if y[i] == 0 else 4
        U[i, lo + rng.choice(4, 3, replace=False)] = 1.0
    U += rng.normal(0, 0.03, U.shape)
    return U, y


def run_rc(U, tau):
    a = np.exp(-1.0 / tau)
    X = np.zeros_like(U)
    x = np.zeros(len(U))
    for k in range(U.shape[1]):
        x = a * x + (1 - a) * U[:, k]
        X[:, k] = x
    return X[:, :, None]  # (시행, 칸, 상태 1개)


def run_esn(U, seed, n=30, rho=0.9, leak=0.3):
    rng = np.random.default_rng(seed + 100)
    W = rng.normal(0, 1, (n, n))
    W *= rho / max(abs(np.linalg.eigvals(W)))
    w_in = rng.uniform(-1, 1, n)
    b = rng.uniform(-0.2, 0.2, n)
    X = np.zeros((len(U), U.shape[1], n))
    x = np.zeros((len(U), n))
    for k in range(U.shape[1]):
        x = (1 - leak) * x + leak * np.tanh(x @ W.T + U[:, k:k + 1] * w_in + b)
        X[:, k] = x
    return X


def cv_accuracy(F, y, seed, folds=5, lam=1.0):
    rng = np.random.default_rng(seed)
    idx0, idx1 = rng.permutation(np.where(y == 0)[0]), rng.permutation(np.where(y == 1)[0])
    parts = [np.concatenate([idx0[f::folds], idx1[f::folds]]) for f in range(folds)]
    accs = []
    for f in range(folds):
        te = parts[f]
        tr = np.concatenate([parts[g] for g in range(folds) if g != f])
        mu, sd = F[tr].mean(0), F[tr].std(0) + 1e-12
        A = (F[tr] - mu) / sd
        A = np.hstack([A, np.ones((len(A), 1))])
        t = 2.0 * y[tr] - 1
        w = np.linalg.solve(A.T @ A + lam * np.eye(A.shape[1]), A.T @ t)
        B = np.hstack([(F[te] - mu) / sd, np.ones((len(te), 1))])
        pred = (B @ w > 0).astype(int)
        accs.append(np.mean([np.mean(pred[y[te] == c] == c) for c in (0, 1)]))  # 균형 정확도
    return float(np.mean(accs)), float(np.std(accs))


def main():
    # Windows 명령 프롬프트(cp949)에서 못 쓰는 글자는 ?로 바꿔 멈추지 않게
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", help="결과 폴더 (예: runs/s2)")
    ap.add_argument("--taus", default="0.3,1,3,10,100", help="R–C 시간상수 목록 (칸 단위)")
    ap.add_argument("--n", type=int, default=200, help="시행 수 (짝수)")
    ap.add_argument("--noise", type=float, default=0.01, help="읽는 상태에 더하는 잡음의 표준편차")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    taus = [float(v) for v in a.taus.split(",")]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    U, y = make_task(a.n, a.seed)
    rng = np.random.default_rng(a.seed + 7)
    end = slice(8, 12)

    systems = [("no memory", "-", U[:, :, None])]
    systems += [("R-C", f"tau = {tau:g}", run_rc(U, tau)) for tau in taus]
    systems.append(("reservoir", "30 nodes", run_esn(U, a.seed)))

    rows = []
    for name, setting, X in systems:
        S = X + rng.normal(0, a.noise, X.shape)
        F = S[:, end].reshape(len(S), -1)
        m, s = cv_accuracy(F, y, a.seed)
        # label shuffle: 정답을 20번 무작위로 섞어 같은 계산을 한 평균 (한 번만 섞으면 우연히 높거나 낮게 나옴)
        sh = float(np.mean([cv_accuracy(F, rng.permutation(y), a.seed)[0] for _ in range(20)]))
        rows.append({"system": name, "setting": setting, "end_only_bacc": round(m, 3), "sd": round(s, 3),
                     "shuffled_labels": round(sh, 3)})

    with open(out / "s2_table.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"task: {a.n} trials, readout = last 4 steps (8-11), readout noise {a.noise:g}, chance = 0.50")
    print()
    from common import print_table
    print_table(["model", "setting", "balanced|accuracy", "+/-", "label|shuffle"],
                [[r["system"], r["setting"], f"{r['end_only_bacc']:.2f}", f"{r['sd']:.2f}",
                  f"{r['shuffled_labels']:.2f}"] for r in rows], left=(0, 1))
    print()
    print("table:", out / "s2_table.csv")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from common import korean_plot
        korean_plot()
    except ImportError:
        print("matplotlib is not installed: plots skipped (python -m pip install matplotlib)")
        return
    from matplotlib.lines import Line2D
    # 입력 예: 두 pattern에서 한 개씩. 모든 P1 그림은 가로 8인치(같은 글씨 크기로 보이게)
    fig0, axs = plt.subplots(2, 1, figsize=(8, 4.2), sharex=True, sharey=True)
    for ax, c, tag in zip(axs, (0, 1), ("(a) pattern 0: 큰 입력 3번이 앞쪽 4칸(0–3) 안에",
                                        "(b) pattern 1: 큰 입력 3번이 가운데 4칸(4–7) 안에")):
        u = U[np.where(y == c)[0][0]]
        hi = u > 0.5
        ax.bar(range(12), u, color=np.where(hi, "#2b59c3", "#b9c6e4"), width=0.75)
        ax.axvspan(7.5, 11.5, color="#fff3c4", zorder=0)
        ax.set_title(tag)
        ax.set_ylabel("input")
        ax.set_ylim(0, 1.5)
        ax.text(9.5, 1.45, "readout 구간 (8–11)", ha="center", va="top", color="#7a5a00")
    axs[1].set_xticks(range(12))
    axs[1].set_xlabel("time step (칸)")
    fig0.tight_layout()
    fig0.savefig(out / "s2_inputs.png")
    plt.close(fig0)

    # 결과: 위 = τ에 따른 balanced accuracy (산 모양), 아래 = τ 세 개의 state 곡선을 칸마다 따로
    fig = plt.figure(figsize=(8, 7.4))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.15, 1], hspace=0.75, wspace=0.32)
    ax1 = fig.add_subplot(gs[0, :])
    rc = [r for r in rows if r["system"] == "R-C"]
    ax1.axhline(0.5, color="0.75", lw=0.9)
    ax1.axhline(rows[0]["end_only_bacc"], color="0.45", ls=":", lw=1.5)
    ax1.axhline(rows[-1]["end_only_bacc"], color="#c27c0e", ls="--", lw=1.5)
    ax1.errorbar(taus, [r["end_only_bacc"] for r in rc], yerr=[r["sd"] for r in rc], fmt="o-", color="#2b59c3",
                 capsize=3, lw=2, ms=6)
    ax1.set_xscale("log")
    ax1.set_xticks(taus)
    ax1.set_xticklabels([f"{t:g}" for t in taus])
    ax1.minorticks_off()
    ax1.set_ylim(0.4, 1.06)
    ax1.set_xlabel("R–C time constant τ (칸)")
    ax1.set_ylabel("balanced accuracy")
    ax1.set_title("(a) τ를 바꾸면: readout 구간만 보고 맞힌 비율", pad=30)
    ax1.legend(handles=[Line2D([], [], color="#2b59c3", marker="o", lw=2, label="R–C (τ마다 한 점)"),
                        Line2D([], [], color="0.45", ls=":", lw=1.5, label=f"no memory {rows[0]['end_only_bacc']:.2f} (≈ chance)"),
                        Line2D([], [], color="#c27c0e", ls="--", lw=1.5, label=f"reservoir {rows[-1]['end_only_bacc']:.2f}")],
               loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, frameon=False, borderaxespad=0.2)
    show = [taus[0], taus[len(taus) // 2], taus[-1]]
    notes = ["금방 식음", "가운데 쪽이 더 남음", "천천히 쌓이기만 함"]
    for j, (tau, note) in enumerate(zip(show, notes)):
        ax = fig.add_subplot(gs[1, j])
        X = run_rc(U, tau)[:, :, 0]
        m0, m1 = X[y == 0].mean(0), X[y == 1].mean(0)
        ax.axvspan(7.5, 11.5, color="#fff3c4", zorder=0)
        ax.plot(range(12), m0, color="#2b59c3", lw=1.8)
        ax.plot(range(12), m1, color="#c0521c", lw=1.8, ls="--")
        ax.set_ylim(0, max(m0.max(), m1.max()) * 1.18)
        ax.set_xticks([0, 4, 8, 11])
        ax.set_title(f"({'bcd'[j]}) τ = {tau:g}: {note}", fontsize=10.5)
        ax.set_xlabel("time step (칸)")
        if j == 0:
            ax.set_ylabel("R–C state")
    fig.legend(handles=[Line2D([], [], color="#2b59c3", lw=1.8, label="pattern 0 평균 (큰 입력이 앞쪽)"),
                        Line2D([], [], color="#c0521c", lw=1.8, ls="--", label="pattern 1 평균 (큰 입력이 가운데)"),
                        matplotlib.patches.Patch(color="#fff3c4", label="readout 구간")],
               loc="center", bbox_to_anchor=(0.5, 0.455), ncol=3, frameon=False)
    fig.savefig(out / "s2_memory.png")
    print("plots:", out / "s2_inputs.png", "|", out / "s2_memory.png")


if __name__ == "__main__":
    main()
