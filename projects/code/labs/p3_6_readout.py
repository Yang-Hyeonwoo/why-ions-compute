# ============================================================
# P3 실습 6 · 모은 state로 판단 식(readout) 학습하기
#
# 전체 과정:
#
#   실습 5의 state (trial 80개 × pulse 48개)
#         ↓
#   마지막 4칸(8–11)의 16개만 feature로 꺼내기  (END_ONLY = True)
#         ↓
#   연습 56개로 weight 정하기:
#     칸마다 평균 0·크기 1로 맞추고(standardization)
#     점수 = Σ weight × feature + bias,  점수 > 0 이면 class 1
#         ↓
#   시험 24개로 채점: balanced accuracy, confusion matrix
#   정답지를 섞어 같은 일을 20번 (label shuffle 점검)
#         ↓
#   b_model.joblib로 저장 → 실습 7이 board용 파일로 바꾼다
#         ↓
#   [그림] confusion matrix + 시험 trial마다의 점수
# ============================================================

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

import joblib                                       # 학습 결과를 파일로 저장
import readout                                      # 학습·채점·label shuffle (P2와 같은 공용 코드)


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

MOCK = True              # True: mock board로 모은 것 / False: 진짜 board로 모은 것
END_ONLY = True          # True: 마지막 4칸 feature만 / False: 48개 전부
EXTRA_NOISE_NA = 0       # 측정이 이만큼(nA) 더 흔들렸다면? 0 = 그대로
SEED = 0

BASE = CODE / "runs" / ("p3_mock" if MOCK else "p3")
RUN_DIR = BASE / "b_dev01"
MODEL_PATH = BASE / "b_model.joblib"


# ============================================================
# 2. state와 정답 읽기
# ============================================================

ck = np.load(RUN_DIR / "checkpoint.npz")
task = np.load(BASE / "task.npz")
F, y = ck["S"].copy(), task["y"]
done = ck["done"]

if EXTRA_NOISE_NA:
    F += np.random.default_rng(SEED).normal(0, EXTRA_NOISE_NA, F.shape)

# end_cols = 마지막 4칸의 열 번호: 칸 8의 pulse 4개 → 32, 33, 34, 35 … 칸 11 → 44–47
cols = task["end_cols"] if END_ONLY else None
if cols is not None:
    F = F[:, cols]

# 아직 안 잰 trial은 빼고 연습·시험으로 나눈다 (나누기는 실습 4에서 정해 둠)
tr = [i for i in task["train_idx"] if done[i]]
te = [i for i in task["test_idx"] if done[i]]
print(f"train {len(tr)} trials, test {len(te)} trials (skipped, not measured: {int((~done).sum())})")
print(f"features per trial : {F.shape[1]} ({'last 4 steps x 4 mask' if END_ONLY else 'all 12 steps x 4 mask'})")


# ============================================================
# 3. 학습 (readout.fit_select)
# ============================================================
#
#   C = weight를 얼마나 크게 허용할지 (작을수록 조심스러운 식).
#   연습 데이터 안에서 다시 5조각으로 나눠 C 13가지를 시험해 보고 가장 좋은 것을 고른다.
#   시험 데이터는 이 고르기에 쓰지 않는다 (시험 문제를 미리 보면 안 되니까).
# ============================================================

model, search = readout.fit_select(F[tr], y[tr])


# ============================================================
# 4. 시험 채점과 점검
# ============================================================

res = readout.evaluate(model, F[te], y[te])
res["chosen_C"] = float(search.best_params_["lr__C"])
res["label_shuffle_bal_acc"], res["label_shuffle_sd"] = readout.label_shuffle_check(F[tr], y[tr], None, F[te], y[te])

print(f"balanced accuracy  {res['balanced_accuracy']:.2f}   (chance = 0.50)")
print(f"confusion matrix   {res['confusion']}   (row = true class, column = predicted)")
print(f"label shuffle      {res['label_shuffle_bal_acc']:.2f} +/- {res['label_shuffle_sd']:.2f}   (20 shuffles; should be near chance)")
print(f"chosen C           {res['chosen_C']:.3g}")


# ============================================================
# 5. 저장 (실습 7의 export가 이 파일을 읽는다)
# ============================================================

if EXTRA_NOISE_NA:
    # 잡음을 일부러 더한 '만약에' 실행은 저장하지 않는다 (실습 7이 엉뚱한 식을 읽지 않게)
    print("not saved (EXTRA_NOISE_NA is not 0: what-if run only)")
else:
    col_text = ",".join(map(str, cols)) if cols is not None else None
    joblib.dump(dict(model=model, cols=col_text, result=res), MODEL_PATH)
    print(f"saved: {MODEL_PATH.relative_to(CODE).as_posix()}")


# ============================================================
# 6. 그림: confusion matrix + 시험 trial마다 점수
# ============================================================

score = model.decision_function(F[te])            # 점수 > 0 이면 class 1
fig, ax = plt.subplots(1, 2, figsize=(8, 3.8), gridspec_kw={"width_ratios": [1, 1.7]})

cm = np.array(res["confusion"])
ax[0].imshow(cm, cmap="Blues", vmin=0)
for i in range(2):
    for j in range(2):
        ax[0].text(j, i, cm[i, j], ha="center", va="center", fontsize=15,
                   color="white" if cm[i, j] > cm.max() / 2 else "#0f1b33")
ax[0].set_xticks([0, 1], ["0", "1"])
ax[0].set_yticks([0, 1], ["0", "1"])
ax[0].set_xlabel("판단한 class")
ax[0].set_ylabel("정답 class")
ax[0].set_title("confusion matrix", loc="left")
for s in ("top", "right"):
    ax[0].spines[s].set_visible(True)

yte = y[te]
colors = {0: "#2b59c3", 1: "#d9962a"}
for c in (0, 1):
    idx = np.where(yte == c)[0]
    ax[1].plot(idx, score[idx], "o", color=colors[c], ms=6, label=f"정답 class {c}")
ax[1].axhline(0, color="#c0392b", ls="--", lw=1.2, label="점수 0 (위 = class 1)")
ax[1].set_xlabel("시험 trial 순서")
ax[1].set_ylabel("점수")
ax[1].set_title(f"시험 {len(te)}개의 점수: balanced accuracy {res['balanced_accuracy']:.2f}", loc="left")

fig.tight_layout(rect=(0, 0.08, 1, 1))
fig.legend(*ax[1].get_legend_handles_labels(), loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.0))

plt.show()
