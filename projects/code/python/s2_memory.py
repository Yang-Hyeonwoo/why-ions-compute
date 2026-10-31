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

    systems = [("기억 없음 (상태 = 지금 입력)", "-", U[:, :, None])]
    systems += [("R-C 하나", f"tau = {tau:g}칸", run_rc(U, tau)) for tau in taus]
    systems.append(("작은 reservoir (노드 30)", "rho 0.9, leak 0.3", run_esn(U, a.seed)))

    rows = []
    for name, setting, X in systems:
        S = X + rng.normal(0, a.noise, X.shape)
        F = S[:, end].reshape(len(S), -1)
        m, s = cv_accuracy(F, y, a.seed)
        sh, _ = cv_accuracy(F, rng.permutation(y), a.seed)
        rows.append({"system": name, "setting": setting, "end_only_bacc": round(m, 3), "sd": round(s, 3),
                     "shuffled_labels": round(sh, 3)})

    with open(out / "s2_table.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"시행 {a.n}개, 읽기 잡음 {a.noise}, 끝 4칸(8-11)만 읽기, 찍기 = 0.50")
    for r in rows:
        print(f"  {r['system']:<26} {r['setting']:<16} 균형 정확도 {r['end_only_bacc']:.2f} +/- {r['sd']:.2f}"
              f"   라벨 섞기 {r['shuffled_labels']:.2f}")
    print("표:", out / "s2_table.csv")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from common import korean_plot
        korean_plot()
    except ImportError:
        print("matplotlib이 없어 그래프는 건너뜀")
        return
    # 먼저 과제 그림: 두 패턴의 입력 한 개씩 (높은 값 3개의 위치만 다르고, 읽는 끝 4칸은 둘 다 낮은 값 + 잡음)
    fig0, axs = plt.subplots(2, 1, figsize=(6.4, 3.4), sharex=True, sharey=True)
    for ax, c, tag in zip(axs, (0, 1), ("(a) 패턴 0: 높은 값 3개가 앞쪽(0–3칸)", "(b) 패턴 1: 높은 값 3개가 뒤쪽(4–7칸)")):
        u = U[np.where(y == c)[0][0]]
        hi = u > 0.5
        ax.bar(range(12), u, color=np.where(hi, "#2b59c3", "#b9c6e4"), width=0.75)
        ax.axvspan(7.5, 11.5, color="#fff3c4", zorder=0)
        ax.set_title(tag, fontsize=9, loc="left")
        ax.set_ylabel("입력", fontsize=8)
        ax.set_ylim(0, 1.25)
    axs[0].text(9.5, 1.18, "읽는 칸 (8–11): 두 패턴 모두 낮은 값", ha="center", va="top", fontsize=8)
    axs[1].set_xticks(range(12))
    axs[1].set_xlabel("칸 (시간 순서)")
    fig0.tight_layout()
    fig0.savefig(out / "s2_inputs.png", dpi=130)
    plt.close(fig0)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4.0))
    rc = [r for r in rows if r["system"] == "R-C 하나"]
    ax1.errorbar(taus, [r["end_only_bacc"] for r in rc], yerr=[r["sd"] for r in rc], fmt="o-", color="#2b59c3",
                 capsize=3, label="R–C 하나")
    ax1.axhline(rows[0]["end_only_bacc"], color="0.5", ls=":", label="기억 없음")
    ax1.axhline(rows[-1]["end_only_bacc"], color="#c27c0e", ls="--", label="작은 reservoir")
    ax1.axhline(0.5, color="0.8", lw=0.8)
    ax1.set_xscale("log")
    ax1.set_ylim(0.4, 1.02)
    ax1.set_xlabel("R–C 시간상수 τ (칸)")
    ax1.set_ylabel("끝만 읽기 균형 정확도")
    ax1.set_title("(a) τ에 따른 정확도", fontsize=10, loc="left")
    ax1.legend(fontsize=8, loc="lower center")
    show = [taus[0], taus[len(taus) // 2], taus[-1]]
    cols = ["#9db3e8", "#2b59c3", "#16306b"]
    for tau, c in zip(show, cols):
        X = run_rc(U, tau)[:, :, 0]
        ax2.plot(range(12), X[y == 0].mean(0), color=c, lw=1.6)
        ax2.plot(range(12), X[y == 1].mean(0), color=c, lw=1.6, ls="--")
    ax2.axvspan(7.5, 11.5, color="#fff3c4", zorder=0)
    ax2.text(9.5, ax2.get_ylim()[1] * 0.97, "읽는 칸", ha="center", va="top", fontsize=8)
    ax2.set_xlabel("칸")
    ax2.set_ylabel("R–C 상태 (두 패턴 평균)")
    ax2.set_title("(b) R–C 상태: 색 = τ, 선 = 패턴", fontsize=10, loc="left")
    # 범례는 곡선을 가리지 않게 그래프 아래로: 색(τ)과 선 모양(패턴)을 나눠서
    from matplotlib.lines import Line2D
    h_tau = [Line2D([], [], color=c, lw=2, label=f"τ = {tau:g}") for tau, c in zip(show, cols)]
    h_pat = [Line2D([], [], color="0.3", lw=1.6, label="패턴 0 (앞쪽)"),
             Line2D([], [], color="0.3", lw=1.6, ls="--", label="패턴 1 (뒤쪽)")]
    ax2.legend(handles=h_tau + h_pat, fontsize=7.5, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.2),
               handlelength=1.6, columnspacing=0.9,
               frameon=False)
    fig.tight_layout()
    fig.savefig(out / "s2_memory.png", dpi=130)
    print("그래프:", out / "s2_inputs.png", "/", out / "s2_memory.png")


if __name__ == "__main__":
    main()
