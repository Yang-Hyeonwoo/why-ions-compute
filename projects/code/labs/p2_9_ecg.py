# ============================================================
# P2 실습 9 · (선택) 진짜 심전도에서 박동을 잘라 입력 만들기
#
# 전체 과정:
#
#   PhysioNet의 MIT-BIH 부정맥 기록을 인터넷에서 내려받기 (처음 한 번, 수 분)
#         ↓
#   기록마다: 기준선 흔들림 거르기 → 360 Hz를 36 Hz로 줄이기
#            → 전문가가 표시한 R 봉우리 앞 0.25초 ~ 뒤 0.45초를 잘라 박동 하나 (25칸)
#         ↓
#   박동 이름표: N 묶음(비이소성) = class 0, V 묶음(심실 이소성) = class 1
#   train 기록 묶음과 test 기록 묶음은 사람이 겹치지 않게 (201과 202는 같은 사람)
#         ↓
#   0–1로 크기를 맞춰 저장 → runs\ecg_set.npz
#   (실습 2의 TASK_NAME = "ecg_set"으로 소자에 걸고, 실습 3으로 채점)
#         ↓
#   그래프: N 묶음과 V 묶음 박동의 모양
#
# 필요: 인터넷, wfdb package (python -m pip install wfdb)
# ============================================================

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게
from ecg_prep import splits, collect, balanced_pick   # python/ecg_prep.py의 함수들


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

N_TRAIN = 200        # train: class마다 박동 수
N_TEST = 100         # test: class마다 박동 수
FS_OUT = 36.0        # 줄인 뒤 sampling rate (Hz). 박동 하나 = 0.7초 × 36 = 25칸
QUICK = False        # True면 기록 몇 개만 내려받아 빨리 흐름만 확인 (점수용 아님)
OUT_NAME = "ecg_set" # 저장 이름 → runs\ecg_set.npz


# ============================================================
# 2. 기록 내려받아 박동 자르기 (시간이 걸립니다. 화면이 멈춘 듯 보여도 기다립니다)
# ============================================================

tr_recs, te_recs = splits(strict=True)           # 202는 test에서 빠짐 (201과 같은 사람)
if QUICK:
    tr_recs, te_recs = tr_recs[:3], te_recs[:3]
print(f"records    : train {len(tr_recs)}, test {len(te_recs)} (downloading...)")
Xtr, ytr, gtr, rtr = collect(tr_recs, FS_OUT)
Xte, yte, gte, rte = collect(te_recs, FS_OUT)

rng = np.random.default_rng(1)
i, j = balanced_pick(ytr, N_TRAIN, rng), balanced_pick(yte, N_TEST, rng)
lo, hi = np.percentile(Xtr[i], [1, 99])          # 크기 기준은 train 박동으로만 정한다
scale = lambda X: np.clip((X - lo) / (hi - lo), 0, 1)
U = np.r_[scale(Xtr[i]), scale(Xte[j])]
y = np.r_[ytr[i], yte[j]]
groups = np.r_[gtr[i], gte[j]]
n = len(i)


# ============================================================
# 3. 저장 (실습 2·3이 읽는 형식: U, y, groups, train_idx, test_idx)
# ============================================================

out = CODE / "runs" / f"{OUT_NAME}.npz"
out.parent.mkdir(exist_ok=True)
np.savez(out, U=U, y=y, groups=groups, record=np.r_[rtr[i], rte[j]],
         train_idx=np.arange(n), test_idx=np.arange(n, len(U)), scale_lo=lo, scale_hi=hi, fs=FS_OUT,
         end_cols=np.arange(U.shape[1] * 4),       # ECG는 박동 전체를 읽는다 (END_ONLY = False로 채점)
         class_names=np.array(["0 = N group (non-ectopic)", "1 = V group (ventricular ectopic)"]))
both = sorted(set(gtr[i]) & set(gte[j]))
print(f"beats      : {U.shape[0]} x {U.shape[1]} steps, train {n} / test {len(U) - n}")
print(f"class 0 / 1: {np.sum(y == 0)} / {np.sum(y == 1)}")
print(f"people in both train and test: {both or 'none'}")
print(f"saved      : runs/{OUT_NAME}.npz")


# ============================================================
# 4. 그래프: N 묶음과 V 묶음 박동의 모양
# ============================================================

t = (np.arange(U.shape[1]) - round(0.25 * FS_OUT)) / FS_OUT * 1000     # R 봉우리 = 0 ms
fig, axs = plt.subplots(1, 2, figsize=(8, 3.8), sharey=True)
for ax, c, col, name in [(axs[0], 0, "#2b59c3", "class 0: N 묶음"), (axs[1], 1, "#e08a3c", "class 1: V 묶음")]:
    beats = U[:n][y[:n] == c]
    for b in beats[:15]:
        ax.plot(t, b, color=col, lw=0.6, alpha=0.35)
    ax.plot(t, beats.mean(0), color=col, lw=2.5)
    ax.axvline(0, color="0.8", lw=0.8, ls=":")
    ax.set_title(f"{name} (train {len(beats)}개)", loc="left")
    ax.set_xlabel("R 봉우리 기준 시간 (ms)")
axs[0].set_ylabel("입력 u (0–1)")
fig.tight_layout()

plt.show()   # 그림 창을 닫으면 프로그램이 끝납니다.
