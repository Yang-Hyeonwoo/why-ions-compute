# ============================================================
# P1 실습 7 · readout 채점: 마지막 4칸 state만 보고 맞힐 수 있나
#
# 전체 과정:
#
#   실습 5의 trial 200개 → 실습 6의 R–C에 넣기 (τ 하나)
#         ↓
#   마지막 4칸(8–11)의 state 4개만 꺼내기
#   + 측정기 오차(readout noise) 더하기
#         ↓
#   readout = "state 4개에 무게를 곱해 더한 값이 0보다 크면 pattern 1"
#   무게(weight)는 연습 문제로 정한다 (선형 분류, ridge)
#         ↓
#   5-fold cross-validation: 연습 160개 / 시험 40개를 다섯 번 바꿔 가며
#         ↓
#   balanced accuracy (맞힌 비율) + label shuffle (정답지 섞기 점검)
#         ↓
#   τ를 여러 개로 반복  →  [그림] τ에 따른 맞힌 비율 (산 모양?)
# ============================================================

import numpy as np
import matplotlib.pyplot as plt


# ============================================================
# 0. 그림 설정 — 건드리지 않아도 됩니다
# ============================================================

plt.rcParams.update({
    "font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 11,
    "legend.frameon": False, "axes.spines.top": False, "axes.spines.right": False,
})


# ============================================================
# 1. 바꿔 볼 수 있는 설정값  ← 여기를 바꿔 보세요
# ============================================================

TAUS = [0.3, 1, 3, 10, 100]   # 비교할 τ 목록 (칸)
NOISE = 0.01                  # readout noise: state를 읽을 때 생기는 오차의 크기
N_TRIALS = 200
SEED = 1


# ============================================================
# 2. trial 만들기 · R–C (실습 5·6과 같은 코드)
# ============================================================

def make_task(n, seed, n_steps=12, noise=0.03):
    rng = np.random.default_rng(seed)
    U = np.full((n, n_steps), 0.1)
    y = np.arange(n) % 2
    rng.shuffle(y)
    for i in range(n):
        start = 0 if y[i] == 0 else 4
        U[i, start + rng.choice(4, 3, replace=False)] = 1.0
    U += rng.normal(0, noise, U.shape)
    return U, y


def run_rc(U, tau):
    a = np.exp(-1.0 / tau)
    X = np.zeros_like(U)
    state = np.zeros(len(U))
    for k in range(U.shape[1]):
        state = a * state + (1 - a) * U[:, k]
        X[:, k] = state
    return X


# ============================================================
# 3. readout: 선형 분류 (ridge)
# ============================================================
#
#   점수 = w1·state8 + w2·state9 + w3·state10 + w4·state11 + b
#   점수 > 0 이면 pattern 1, 아니면 pattern 0
#
#   무게 w는 '연습 문제'의 정답에 가장 잘 맞게 정한다 (최소제곱 + 작은 벌점 LAM).
#   그 전에 연습 문제 기준으로 칸마다 평균 0, 크기 1로 맞춘다 (standardization).
#   시험 문제의 정답은 무게를 정할 때 절대 보지 않는다.
# ============================================================

LAM = 1.0

def fit(F, y):
    mu, sd = F.mean(0), F.std(0) + 1e-12
    A = np.hstack([(F - mu) / sd, np.ones((len(F), 1))])       # 마지막 열 = b
    target = 2.0 * y - 1                                        # 정답 0/1 → −1/+1
    w = np.linalg.solve(A.T @ A + LAM * np.eye(A.shape[1]), A.T @ target)
    return mu, sd, w


def predict(model, F):
    mu, sd, w = model
    A = np.hstack([(F - mu) / sd, np.ones((len(F), 1))])
    return (A @ w > 0).astype(int)


def balanced_accuracy(pred, y):
    """pattern 0 문제와 pattern 1 문제를 따로 채점해서 평균"""
    return np.mean([np.mean(pred[y == c] == c) for c in (0, 1)])


# ============================================================
# 4. 5-fold cross-validation
# ============================================================
#
#   200문제를 다섯 묶음으로 나눈다 (묶음마다 pattern 0·1 반반).
#   묶음 하나를 시험, 나머지 넷을 연습 → 다섯 번 → 점수 다섯 개의 평균.
# ============================================================

def cross_validate(F, y, seed, folds=5):
    rng = np.random.default_rng(seed)
    i0 = rng.permutation(np.where(y == 0)[0])
    i1 = rng.permutation(np.where(y == 1)[0])
    parts = [np.concatenate([i0[f::folds], i1[f::folds]]) for f in range(folds)]
    scores = []
    for f in range(folds):
        test = parts[f]
        train = np.concatenate([parts[g] for g in range(folds) if g != f])
        model = fit(F[train], y[train])
        scores.append(balanced_accuracy(predict(model, F[test]), y[test]))
    return np.mean(scores), np.std(scores)


# ============================================================
# 5. 모형마다 채점
# ============================================================

U, y = make_task(N_TRIALS, SEED)
rng = np.random.default_rng(SEED + 7)
end = slice(8, 12)

def readout_features(X):
    """마지막 4칸 state + 측정기 오차"""
    return X[:, end] + rng.normal(0, NOISE, X[:, end].shape)

models = [("no memory", "-", U)]                                 # state = 지금 입력
models += [("R-C", f"tau = {tau:g}", run_rc(U, tau)) for tau in TAUS]

print("=" * 60)
print(f"readout = last 4 steps, readout noise {NOISE}, chance = 0.50")
print("=" * 60)
print()
print("model      setting     balanced   +/-    label")
print("                       accuracy          shuffle")
print("---------  ---------  ---------  ----  -------")

results = []
for name, setting, X in models:
    F = readout_features(X)
    acc, sd = cross_validate(F, y, SEED)

    # label shuffle: 정답지를 무작위로 섞고 똑같이 → 0.5 근처가 정상 (20번 평균)
    shuffled = np.mean([cross_validate(F, rng.permutation(y), SEED)[0] for _ in range(20)])

    results.append((name, setting, acc, sd, shuffled))
    print(f"{name:<9}  {setting:<9}     {acc:.2f}     {sd:.2f}    {shuffled:.2f}")


# ============================================================
# 6. [그림] τ에 따른 맞힌 비율
# ============================================================

rc = [r for r in results if r[0] == "R-C"]
fig, ax = plt.subplots(figsize=(8, 4.2))
ax.axhline(0.5, color="0.75", lw=1, ls=":", label="chance 0.50 (찍기)")
ax.axhline(results[0][2], color="0.45", ls="--", lw=1.2, label=f"no memory {results[0][2]:.2f}")
ax.errorbar(TAUS, [r[2] for r in rc], yerr=[r[3] for r in rc], fmt="o-", color="#2b59c3",
            lw=2, ms=7, capsize=3, label="R–C (τ마다 한 점)")
ax.set_xscale("log")
ax.set_xticks(TAUS, [f"{t:g}" for t in TAUS])
ax.minorticks_off()
ax.set_ylim(0.4, 1.05)
ax.set_xlabel("R–C time constant τ (칸, 로그 눈금)")
ax.set_ylabel("balanced accuracy")
ax.set_title(f"마지막 4칸 state만 보고 맞힌 비율 (readout noise {NOISE})", loc="left")
fig.tight_layout(rect=(0, 0.08, 1, 1))
fig.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=3)

plt.show()
