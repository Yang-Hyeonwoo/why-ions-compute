# ============================================================
# P2 실습 3 · readout 채점: 마지막 4칸의 전류만 보고 class를 맞힐 수 있나
#
# 전체 과정:
#
#   실습 2가 저장한 측정 기록 (runs\mock_memory, runs\mock_resistor) 읽기
#   + 실습 1의 시험 문제 파일 (정답 · 연습/시험 나누기)
#         ↓
#   END_ONLY = True 이면 숫자 48개 중 마지막 4칸의 16개만 쓴다
#         ↓
#   readout = "숫자 16개에 무게를 곱해 더한 점수가 0보다 크면 class 1"
#   무게는 연습 문제(train 28개)로만 정한다 (logistic regression)
#         ↓
#   시험 문제(test 12개)로 채점 → balanced accuracy
#   점검: 정답지를 섞고 똑같이 하면 0.5 근처여야 정상 (label shuffle)
#         ↓
#   그래프 ① 측정마다 점수   ② 시험 문제 하나하나의 readout 점수
# ============================================================

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게
from readout import fit_select, evaluate, label_shuffle_check   # python/readout.py의 채점 함수


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

RUNS = ["mock_memory", "mock_resistor"]   # 채점할 측정 폴더 (runs 안). 진짜 측정이면 "a2_dev01" 등
TASK_NAME = "task_p2"                     # 그 측정에 쓴 시험 문제 파일
END_ONLY = True                           # True = 마지막 4칸(숫자 16개)만, False = 48개 전부
N_SHUFFLE = 20                            # 정답지를 몇 번 섞어 점검할지 (많을수록 느림)


# ============================================================
# 2. 시험 문제 파일: 정답 y, 연습/시험 나누기, 마지막 4칸의 열 번호
# ============================================================

task = np.load(CODE / "runs" / f"{TASK_NAME}.npz")
y, train_idx, test_idx = task["y"], task["train_idx"], task["test_idx"]
groups = task["groups"]              # 같은 사람(ECG)의 박동이 연습·시험에 섞이지 않게 쓰는 번호
end_cols = task["end_cols"]          # [32, 33, …, 47]: 8–11칸의 pulse 16개


# ============================================================
# 3. 측정 하나를 채점하는 순서
# ============================================================
#
# (1) 연습 문제로 무게 정하기 (fit_select)
#     연습 문제를 다시 5묶음으로 나눠 "무게를 얼마나 조심스럽게 정할지(C)"도 고른다.
#     시험 문제는 이 단계에서 절대 보지 않는다 (보면 점수가 부풀어 오른다).
# (2) 시험 문제에 무게를 곱해 답을 내고 채점 (evaluate)
#     balanced accuracy = class 0 문제와 class 1 문제를 따로 채점한 평균
# (3) 정답지를 섞어 같은 일을 N_SHUFFLE번 (label_shuffle_check) → 0.5 근처가 정상
# ============================================================

def score_run(name):
    run = CODE / "runs" / name
    if not (run / "checkpoint.npz").exists():
        raise SystemExit(f"runs/{name} 이 없습니다. 실습 2를 먼저 ▷ 하세요 "
                         f"(mock_resistor는 실습 2에서 MOCK_MODEL = \"resistor\"로 한 번 더).")
    ck = np.load(run / "checkpoint.npz")
    S, done = ck["S"], ck["done"]
    if "y" in ck and not np.array_equal(ck["y"], y):
        raise SystemExit(f"runs/{name} 은 다른 시험 문제로 잰 기록입니다. 실습 2를 다시 ▷ 하세요.")
    F = S[:, end_cols] if END_ONLY else S
    tr = np.array([i for i in train_idx if done[i]])          # 아직 안 잰 trial은 뺀다
    te = np.array([i for i in test_idx if done[i]])
    model, gs = fit_select(F[tr], y[tr], groups[tr])
    res = evaluate(model, F[te], y[te])
    sh_mean, sh_sd = label_shuffle_check(F[tr], y[tr], groups[tr], F[te], y[te], n_perm=N_SHUFFLE)
    score = model.decision_function(F[te])                    # 시험 문제마다 readout 점수 (0보다 크면 class 1)
    return dict(name=name, acc=res["balanced_accuracy"], sh=sh_mean, sh_sd=sh_sd,
                right=int(np.trace(np.array(res["confusion"]))), n=len(te),
                conf=res["confusion"], score=score, y_te=y[te], n_tr=len(tr))


# ============================================================
# 4. 측정마다 채점하고 표로 찍기
# ============================================================

results = [score_run(name) for name in RUNS]

print("=" * 66)
print(f"readout = {'last 4 steps (16 numbers)' if END_ONLY else 'all 48 numbers'}, "
      f"train {results[0]['n_tr']} / test {results[0]['n']}, chance = 0.50")
print("=" * 66)
print("run              test right   balanced   label shuffle")
print("                              accuracy   (should be near 0.5)")
print("---------------  ----------   --------   --------------------")
for r in results:
    print(f"{r['name']:<15}  {r['right']:>4} / {r['n']:<3}     {r['acc']:.2f}       "
          f"{r['sh']:.2f} +/- {r['sh_sd']:.2f}")


# ============================================================
# 5. 그래프 ① 측정마다 점수  ② 시험 문제 하나하나의 readout 점수
# ============================================================

n = len(results)
fig = plt.figure(figsize=(8, 6.8))
gs = fig.add_gridspec(2, n, height_ratios=[1, 1.15], hspace=0.85, wspace=0.35)

ax = fig.add_subplot(gs[0, :])
x = np.arange(n)
ax.bar(x - 0.18, [r["acc"] for r in results], width=0.34, color="#2b59c3", label="balanced accuracy (시험 문제)")
ax.bar(x + 0.18, [r["sh"] for r in results], width=0.34, color="#c9cfd8",
       yerr=[r["sh_sd"] for r in results], capsize=3, label="label shuffle (점검)")
ax.axhline(0.5, color="#c0392b", lw=1, ls=":", label="chance 0.50 (찍기)")
ax.set_xticks(x, [r["name"] for r in results])
ax.set_xlim(-0.6, n - 0.4)
ax.set_ylim(0, 1.12)
ax.set_ylabel("맞힌 비율")
ax.set_title(f"① 측정마다 점수 ({'마지막 4칸만' if END_ONLY else '48개 전부'})", loc="left")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, fontsize=9.5)

for j, r in enumerate(results):
    a = fig.add_subplot(gs[1, j])
    rng = np.random.default_rng(0)
    for c, col, mk in [(0, "#2b59c3", "o"), (1, "#e08a3c", "s")]:
        s = r["score"][r["y_te"] == c]
        a.plot(c + rng.uniform(-0.15, 0.15, len(s)), s, mk, color=col, ms=7, alpha=0.85, ls="none")
    a.axhline(0, color="0.3", lw=1, ls="--")
    a.set_xticks([0, 1], ["정답 0", "정답 1"])
    a.set_xlim(-0.6, 1.6)
    lim = 1.15 * max(1e-9, np.abs(r["score"]).max())
    a.set_ylim(-lim, lim)
    a.set_yticks([])
    a.set_title(f"② {r['name']}: {r['right']}/{r['n']} 맞힘", loc="left", fontsize=10.5)
    if j == 0:
        a.set_ylabel("readout 점수\n(점선 위 = 답 1)")

plt.show()   # 그림 창을 닫으면 프로그램이 끝납니다.
