"""B1b. 같은 끝, 다른 순서 — 버튼 리듬 X/Y를 구별하는 데 '기억'이 필요한가.

X: 누름 시각 0, 0.25, 0.5, 1.5, 2.0 s    Y: 0, 1.0, 1.25, 1.5, 2.0 s
둘 다 5번, 처음→마지막 2.0 s, 마지막 간격 0.5 s. 앞쪽 순서만 다르다.

같은 파일로 다섯 모델을 비교한다(훈련 = 마지막 세션을 뺀 세션, 시험 = 마지막 세션).
  1. 마지막 값만      : 마지막 누름 순간의 입력(항상 1) → 구별 불가가 정상
  2. 횟수·길이        : 누른 횟수와 처음→마지막 길이 → 설계상 같으니 구별 불가가 정상
  3. 간격 규칙        : 첫 간격 하나를 문턱과 비교 (사람이 짠 짧은 규칙)
  4. 누설 노드(τ)     : 소자처럼 누를 때 오르고 쉬면 새는 상태 하나를 마지막 누름 직후에 읽음
  5. 작은 reservoir   : 고정된 무작위 노드 40개(ESN) + 학습한 readout
그다음 시험 세션의 템포(빠르게·느리게)와 손 떨림(간격 흔들림)을 바꿔 어디서 결과가 갈리는지 본다.
이 변형은 기록된 시각을 계산으로 늘리고 흔든 것이다(새 측정이 아님).

    python b1_memory.py --csv data/b1_taps.csv     # 내 기록
    python b1_memory.py --synthetic                 # 합성 데이터로 코드 확인 (data/b1_taps_synthetic.csv도 만든다)
    python b1_memory.py --failures                  # 이 실험에서 나올 수 있는 실패 파형 예시 그림
"""
import argparse
import csv
import os
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PAT = {"X": [0, 0.25, 0.5, 1.5, 2.0], "Y": [0, 1.0, 1.25, 1.5, 2.0]}
FS = 200            # 보드 샘플링 (Hz)
DEBOUNCE = 0.03     # 뗀 뒤 30 ms 안에 다시 붙으면 접점 튐으로 본다
GAP = 1.6           # 이보다 긴 쉼이면 다음 시행
TAUS = (0.1, 0.5, 2.0)
READ_NOISE = 0.01  # reservoir 상태를 읽을 때 더하는 잡음(표준편차)


# ---------------- 합성 데이터 (코드 확인용, 실측 아님) ----------------
def synth_stream(label, n_trials, rng, jitter=0.08, bounce=0.1, miss=0.02):
    """사람이 리듬을 n번 친 것처럼 200 Hz 버튼 줄을 만든다."""
    t_end = 1.0 + n_trials * 4.5
    t = np.arange(0, t_end, 1 / FS)
    btn = np.zeros_like(t, dtype=int)
    start = 1.0
    for _ in range(n_trials):
        iv = np.diff(PAT[label]) * rng.normal(1, jitter, 4)
        times = start + np.concatenate([[0], np.cumsum(iv)])
        for k, s in enumerate(times):
            if rng.random() < miss and k not in (0, 4):
                continue                     # 가끔 한 번을 놓친다
            dur = rng.uniform(0.07, 0.12)
            btn[(t >= s) & (t < s + dur)] = 1
            if rng.random() < bounce:        # 떼는 순간 접점이 한 번 더 붙는다
                b0 = s + dur + 0.008
                btn[(t >= b0) & (t < b0 + 0.006)] = 1
        start = times[-1] + rng.uniform(2.2, 2.8)
    light = 1.2 + 0.02 * rng.standard_normal(len(t))
    return t, btn, light


def write_synthetic(path, seed=7):
    rng = np.random.default_rng(seed)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["session", "label", "n", "time_s", "button", "light_V", "source"])
        for s in ("s1", "s2", "s3"):
            for lab in ("X", "Y"):
                t, b, v = synth_stream(lab, 20, rng)
                for i in range(len(t)):
                    w.writerow([s, lab, i, f"{t[i]:.3f}", b[i], f"{v[i]:.3f}", "synthetic"])
    print("synthetic CSV:", path)


# ---------------- 읽기·시행 나누기 ----------------
def load(path):
    streams = defaultdict(lambda: ([], []))
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            k = (r["session"], r["label"])
            streams[k][0].append(float(r["time_s"]))
            streams[k][1].append(int(r["button"]))
    return {k: (np.array(a), np.array(b)) for k, (a, b) in streams.items()}


def onsets(t, b):
    """누름 시작 시각. 뗀 지 DEBOUNCE 안에 다시 붙은 것은 접점 튐으로 보고 버린다."""
    rise = t[1:][(b[1:] == 1) & (b[:-1] == 0)]
    fall = t[1:][(b[1:] == 0) & (b[:-1] == 1)]
    keep = []
    for x in rise:
        before = fall[fall < x]
        if len(before) and x - before[-1] < DEBOUNCE:
            continue
        keep.append(x)
    return np.array(keep), len(rise) - len(keep)


def trials(streams):
    out, info = [], defaultdict(int)
    for (sess, lab), (t, b) in sorted(streams.items()):
        on, bounced = onsets(t, b)
        info["presses dropped as bounce"] += bounced
        groups, cur = [], [on[0]] if len(on) else []
        for x in on[1:]:
            if x - cur[-1] > GAP:
                groups.append(cur)
                cur = [x]
            else:
                cur.append(x)
        if cur:
            groups.append(cur)
        for g in groups:
            if len(g) == 5:
                out.append((sess, lab, np.array(g) - g[0]))
            else:
                info[f"trials with {len(g)} presses (not 5)"] += 1
    return out, dict(info)


# ---------------- 모델 ----------------
def leaky_state(times, tau, g=0.5):
    x, prev = 0.0, times[0]
    for s in times:
        x *= np.exp(-(s - prev) / tau)
        x += g * (1 - x)
        prev = s
    return x


class ESN:
    def __init__(self, n=40, leak=0.05, rho=0.9, seed=0, dt=0.02):
        r = np.random.default_rng(seed)
        W = r.normal(0, 1, (n, n)) * (r.random((n, n)) < 0.2)
        W *= rho / max(abs(np.linalg.eigvals(W)))
        self.W, self.win, self.leak, self.dt = W, r.uniform(-1, 1, n), leak, dt
        self.noise = np.random.default_rng(seed + 100)

    def state(self, times):
        steps = int(round(times[-1] / self.dt)) + 1
        u = np.zeros(steps)
        u[np.clip(np.round(np.asarray(times) / self.dt).astype(int), 0, steps - 1)] = 1
        x = np.zeros(len(self.win))
        for k in range(steps):
            x = (1 - self.leak) * x + self.leak * np.tanh(self.W @ x + self.win * u[k])
        # 읽기 잡음(ADC 등). 잡음보다 작게 남은 기억은 쓸 수 없다는 점을 반영
        return x + self.noise.normal(0, READ_NOISE, len(x))


def fit_threshold(v, y):
    """1차원 값 하나로 나누는 문턱과 방향을 훈련 데이터에서 고른다."""
    best = (0.0, 0.5, 1)
    for th in np.unique(v):
        for sgn in (1, -1):
            acc = np.mean((sgn * (v - th) > 0) == y)
            if acc > best[0]:
                best = (acc, th, sgn)
    return best[1], best[2]


def features(times, esn):
    iv = np.diff(times)
    return {"last": [1.0], "count": [len(times), times[-1]], "rule": iv[0],
            **{f"tau{t}": leaky_state(times, t) for t in TAUS}, "esn": esn[0].state(times), "esn_fast": esn[1].state(times)}


def evaluate(train, test, esn):
    from sklearn.linear_model import LogisticRegression, RidgeClassifier
    ytr = np.array([lab == "X" for _, lab, _ in train])
    yte = np.array([lab == "X" for _, lab, _ in test])
    Ftr = [features(ts, esn) for *_, ts in train]
    Fte = [features(ts, esn) for *_, ts in test]
    res = {}
    for k in ("last", "count"):
        m = LogisticRegression().fit([f[k] for f in Ftr], ytr) if len(set(np.array([f[k] for f in Ftr]).ravel())) > 1 else None
        pred = m.predict([f[k] for f in Fte]) if m else np.full(len(yte), ytr.mean() >= 0.5)
        res[k] = np.mean(pred == yte)
    for k in ("rule",) + tuple(f"tau{t}" for t in TAUS):
        th, sgn = fit_threshold(np.array([f[k] for f in Ftr]), ytr)
        res[k] = np.mean((sgn * (np.array([f[k] for f in Fte]) - th) > 0) == yte)
    for k in ("esn", "esn_fast"):
        m = RidgeClassifier(alpha=1e-3).fit([f[k] for f in Ftr], ytr)
        res[k] = np.mean(m.predict([f[k] for f in Fte]) == yte)
    return res


NAMES = {"last": "last value only", "count": "count & length", "rule": "first-gap rule",
         **{f"tau{t}": f"leaky node tau={t} s" for t in TAUS}, "esn": "reservoir 40 (slow)", "esn_fast": "reservoir 40 (fast)"}


def vary(test, scale=1.0, jitter=0.0, seed=1):
    r = np.random.default_rng(seed)
    out = []
    for s, lab, ts in test:
        iv = np.diff(ts) * scale * r.normal(1, jitter, 4) if jitter else np.diff(ts) * scale
        out.append((s, lab, np.concatenate([[0], np.cumsum(np.abs(iv))])))
    return out


def main(path, out_png, synthetic):
    tr_all, info = trials(load(path))
    sessions = sorted({s for s, *_ in tr_all})
    if len(sessions) < 2:
        raise SystemExit("세션이 2개 이상 필요합니다(훈련·시험을 세션으로 나눔). --session s1, s2 …로 더 기록하세요.")
    test_s = sessions[-1]
    train = [x for x in tr_all if x[0] != test_s]
    test = [x for x in tr_all if x[0] == test_s]
    from common import print_table
    print(f"{'synthetic' if synthetic else 'measured'} data: {len(tr_all)} trials "
          f"(train {len(train)}: {', '.join(sessions[:-1])} / test {len(test)}: {test_s})")
    for k, v in info.items():
        print(f"  {k}: {v}")
    esn = (ESN(leak=0.05), ESN(leak=0.3))   # 느린 기억(약 0.4 s) / 빠른 기억(약 0.07 s)
    base = evaluate(train, test, esn)
    chance = max(np.mean([lab == "X" for _, lab, _ in test]), np.mean([lab == "Y" for _, lab, _ in test]))
    print(f"chance (always guess the larger class in the test session): {chance:.0%}")
    print()
    print_table(["model", "test accuracy"], [[NAMES[k], f"{v:.0%}"] for k, v in base.items()], left=(0,))
    scales = [0.5, 0.7, 1.0, 1.4, 2.0]
    jits = [0.0, 0.1, 0.2, 0.3]
    show = ("rule", "tau0.5", "esn")
    by_scale = {k: [evaluate(train, vary(test, scale=s), esn)[k] for s in scales] for k in show}
    by_jit = {k: [evaluate(train, vary(test, jitter=j), esn)[k] for j in jits] for k in show}
    print()
    print("test tempo changed (x interval; training stays at 1.0)")
    print_table(["model"] + [f"x{s:g}" for s in scales], [[NAMES[k]] + [f"{v:.0%}" for v in by_scale[k]] for k in show],
                left=(0,))
    print()
    print("hand jitter added (relative SD of intervals)")
    print_table(["model"] + [f"{j:g}" for j in jits], [[NAMES[k]] + [f"{v:.0%}" for v in by_jit[k]] for k in show],
                left=(0,))

    from common import korean_plot
    plt = korean_plot()
    fig = plt.figure(figsize=(8, 7.2))  # 모든 프로젝트 그림은 가로 8인치 (글씨 크기 통일)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.1, 1], hspace=0.55, wspace=0.3)
    ax = [fig.add_subplot(gs[0, :]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])]
    keys = list(base)
    ax[0].barh([NAMES[k] for k in keys][::-1], [base[k] for k in keys][::-1], color="#2b59c3")
    ax[0].axvline(chance, color="#888", ls="--", lw=1)
    ax[0].set_xlim(0, 1.05)
    ax[0].set_title("(a) test session at the same tempo: test accuracy")
    cols = {"rule": "#0f1b33", "tau0.5": "#0e8a83", "esn": "#2b59c3"}
    for k in show:
        ax[1].plot(scales, by_scale[k], "o-", color=cols[k], label=NAMES[k])
        ax[2].plot(jits, by_jit[k], "o-", color=cols[k], label=NAMES[k])
    ax[1].set_xscale("log", base=2)
    ax[1].set_xticks(scales, [str(s) for s in scales])
    ax[1].set_title("(b) test tempo changed")
    ax[1].set_xlabel("interval scale (training = 1)")
    ax[2].set_title("(c) hand jitter added")
    ax[2].set_xlabel("interval jitter (relative SD)")
    for a in ax[1:]:
        a.set_ylim(0.3, 1.05)
        a.axhline(chance, color="#888", ls="--", lw=1)
    ax[1].set_ylabel("test accuracy")
    fig.legend(handles=ax[1].get_lines()[:len(show)], loc="lower center", bbox_to_anchor=(0.5, -0.04), ncol=3, frameon=False)
    fig.suptitle(("synthetic data: for checking the code, not a measurement" if synthetic else f"measured: {os.path.basename(path)}"), fontsize=10, x=0.01, ha="left", color="#6b7280")
    fig.savefig(out_png)
    print("\nplot:", out_png)
    return base


def failures(out_png):
    """접점 튐·누락·포화가 실제 파형에서 어떻게 보이는지 (합성 예시)."""
    from common import korean_plot
    plt = korean_plot()
    t = np.arange(0, 0.6, 1 / FS)
    ok = ((t > 0.1) & (t < 0.2)).astype(int)
    bounce = ok.copy()
    bounce[(t > 0.205) & (t < 0.212)] = 1
    bounce[(t > 0.1) & (t < 0.104)] = 0
    keep = np.ones_like(t, bool)
    keep[60:80] = False
    light = np.clip(0.4 + 3.5 * ((t > 0.25) & (t < 0.45)), 0, 3.3)
    fig, ax = plt.subplots(3, 1, figsize=(8, 6.6))
    ax[0].step(t * 1000, bounce, where="post", color="#2b59c3")
    ax[0].set_title("(a) bounce: 떼는 순간 짧은 두 번째 누름")
    ax[1].step(t[keep] * 1000, ok[keep], where="post", color="#2b59c3", marker=".", ms=3, lw=0.8)
    ax[1].axvspan(300, 400, color="#f3c4b5", alpha=0.5)
    ax[1].set_title("(b) dropped samples: 샘플 번호 n이 건너뜀 (빈 구간)")
    ax[2].plot(t * 1000, light, color="#0e8a83")
    ax[2].axhline(3.3, color="#a33a1c", ls="--", lw=1)
    ax[2].set_title("(c) saturation: 빛 센서 값이 전원 전압에 붙어 평평")
    for a in ax:
        a.set_xlabel("time (ms)")
    fig.suptitle("failure examples: synthetic, not a measurement", fontsize=10, x=0.01, ha="left", color="#6b7280")
    fig.tight_layout()
    fig.savefig(out_png)
    print("plot:", out_png)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(HERE, "data", "b1_taps.csv"))
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--failures", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    if a.failures:
        failures(a.out or os.path.join(HERE, "data", "b1_failures.png"))
    else:
        path = a.csv
        if a.synthetic:
            path = os.path.join(HERE, "data", "b1_taps_synthetic.csv")
            write_synthetic(path)
        main(path, a.out or os.path.join(HERE, "data", "b1_memory" + ("_synthetic" if a.synthetic else "") + ".png"), a.synthetic)
