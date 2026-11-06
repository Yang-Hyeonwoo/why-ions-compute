# ============================================================
# P3 실습 4 · 소자에 걸 입력과 board 설정 파일(config.h) 만들기
#
# 전체 과정:
#
#   설정 파일(config_board…json) 읽기: pulse 높이·길이·mask
#         ↓
#   입력 80줄 만들기 (P1.2와 같은 '큰 입력이 앞쪽이냐 뒤쪽이냐' 과제)
#   → task.npz 로 저장 (정답, 연습/시험 나누기 포함)
#         ↓
#   입력 한 줄(12칸)을 pulse 48개로 바꾸면 어떻게 생겼나 (mask)
#         ↓
#   board가 읽을 config.h 쓰기 (손으로 옮기지 않는다)
#         ↓
#   [그림 1] 입력 80줄   [그림 2] 입력 한 줄 → pulse 48개
#
# board 없이 돕니다. MOCK = True는 연습용 폴더(runs/p3_mock)에,
# MOCK = False는 진짜 측정용(runs/p3, firmware/B5_collect)에 씁니다.
# ============================================================

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

import tasks                                        # 입력 과제 만들기
from common import load_json                        # 설정 파일 읽기
from measure_seq import check_inputs, pulse_plan    # 전압 범위 검사, 입력 → pulse 높이
from make_config_h import write_config_h            # board용 config.h 쓰기


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

MOCK = True          # True: 연습(예시 설정) / False: 내 설정 파일로 진짜 측정 준비
N_PER_CLASS = 40     # class마다 입력 몇 줄 (모두 2배)
SHOW_TRIAL = 0       # 그림 2에서 크게 볼 입력 줄 번호

# MOCK에 따라 정해지는 파일 위치 (바꾸지 않아도 됩니다)
CONFIG = "config_board_example.json" if MOCK else "config_board.json"     # python 폴더 안
BASE = CODE / "runs" / ("p3_mock" if MOCK else "p3")                       # 결과 폴더
CONFIG_H_DIR = BASE / "B5_collect" if MOCK else CODE / "firmware" / "B5_collect"


# ============================================================
# 2. 설정 파일 읽기
# ============================================================
#
#   encoding = 입력(0–1)을 전압으로 바꾸는 규칙
#     V0    : 입력이 0일 때 전압
#     VA    : 입력이 1일 때 더하는 전압
#     mask  : 한 칸을 pulse 몇 개로 나눠, 각각 높이를 몇 배로 할지 (예: 4개)
#     theta : pulse 하나의 길이 (초)
#     rest  : trial 사이 0 V로 쉬는 시간 (초)
# ============================================================

cfg = load_json(CODE / "python" / CONFIG)
enc = cfg["encoding"]
v_limit = cfg["instrument"]["v_limit_V"]
mask = np.array(enc["mask"])
M = len(mask)


# ============================================================
# 3. 입력 80줄 만들기 (tasks.timing_task)
# ============================================================
#
#   한 줄 = 12칸. 기본은 작은 입력 0.2, 큰 입력 1.0을 3칸에.
#   class 0 (early): 큰 입력이 0–3칸에   class 1 (late): 4–7칸에
#   8–11칸은 모두 0.2 → 마지막 4칸 '입력'만 보고는 구별 불가
#   순서를 섞어 두고, 앞 70 %는 연습(train), 뒤 30 %는 시험(test)
# ============================================================

U, y, groups, steps = tasks.timing_task(N_PER_CLASS)
L = U.shape[1]
n_train = int(len(y) * 0.7)
check_inputs(U, enc, v_limit)                      # 전압이 v_limit를 넘으면 여기서 멈춘다

BASE.mkdir(parents=True, exist_ok=True)
np.savez(BASE / "task.npz", U=U, y=y, groups=groups, readout_steps=steps,
         end_cols=tasks.feature_columns(steps, M),
         train_idx=np.arange(n_train), test_idx=np.arange(n_train, len(y)))


# ============================================================
# 4. 입력 한 줄 → pulse 48개 (measure_seq.pulse_plan)
# ============================================================
#
#   칸 하나의 입력 u를 pulse M개로 나눠 건다.
#   pulse j의 높이 = V0 + VA × u × mask[j]
#   mask가 (0.84, 0.43, 0.97, 0.61)이면, 같은 u라도 네 pulse의 높이가 다르다.
#   → 소자가 같은 입력을 네 가지 세기로 받아, 읽는 값(state)도 네 가지가 된다.
#   board도 똑같은 규칙으로 pulse를 만든다 (config.h에 같은 숫자가 들어감).
# ============================================================

volts = np.array(pulse_plan(U[SHOW_TRIAL], enc))
per_trial_s = enc["rest_s"] + L * M * enc["theta_s"]
v_max = max(abs(enc["V0"]), abs(enc["V0"] + enc["VA"] * mask.max()))


# ============================================================
# 5. board용 config.h 쓰기 (make_config_h.write_config_h)
# ============================================================

h_path = write_config_h(enc, L, v_limit, cfg["device"].get("id", ""), str(CONFIG_H_DIR))

print(f"config          : {CONFIG}")
print(f"trials          : {len(y)} (class 0: early {np.sum(y == 0)}, class 1: late {np.sum(y == 1)})")
print(f"train / test    : {n_train} / {len(y) - n_train}")
print(f"readout steps   : {steps.tolist()}")
print(f"pulses / trial  : {L} steps x {M} mask = {L * M}, each {enc['theta_s'] * 1000:.0f} ms")
print(f"time / trial    : rest {enc['rest_s']} s + {L * M} x {enc['theta_s']} s = {per_trial_s:.1f} s")
print(f"largest voltage : {v_max:.2f} V (limit {v_limit} V)")
print(f"saved: {(BASE / 'task.npz').relative_to(CODE).as_posix()}")
print(f"saved: {Path(h_path).relative_to(CODE).as_posix()}")
print()
print(Path(h_path).read_text(encoding="utf-8").rstrip())


# ============================================================
# 6. 그림 1: 입력 80줄 (class별로 모아서)
# ============================================================

order = np.argsort(y, kind="stable")
fig1, ax = plt.subplots(figsize=(8, 3.8))
im = ax.imshow(U[order].T, aspect="auto", cmap="Blues", vmin=0, vmax=1, interpolation="nearest")
ax.axvline(np.sum(y == 0) - 0.5, color="#c0392b", lw=1.5)
ax.add_patch(plt.Rectangle((-0.5, 7.5), len(y), 4, fill=False, edgecolor="#d9962a", lw=2.5))
ax.set_yticks(range(L))
ax.set_ylabel("칸 번호")
ax.set_xlabel("입력 줄 (왼쪽 = class 0 early, 오른쪽 = class 1 late)")
ax.set_title("입력 80줄: 진한 칸 = 큰 입력 1.0, 주황 테두리 = 마지막 4칸", loc="left")
fig1.colorbar(im, ax=ax, label="입력 u", fraction=0.04, pad=0.02)
fig1.tight_layout()


# ============================================================
# 7. 그림 2: 입력 한 줄 → pulse 48개
# ============================================================

fig2, ax2 = plt.subplots(2, 1, figsize=(8, 5), gridspec_kw={"height_ratios": [1, 1.4]})
ax2[0].bar(range(L), U[SHOW_TRIAL], color="#2b59c3", width=0.7)
ax2[0].set_xticks(range(L))
ax2[0].set_ylim(0, 1.15)
ax2[0].set_xlabel("칸 번호")
ax2[0].set_ylabel("입력 u")
ax2[0].set_title(f"입력 {SHOW_TRIAL}번 줄 (정답 class {y[SHOW_TRIAL]})", loc="left")

t_ms = np.arange(L * M) * enc["theta_s"] * 1000
mask_colors = ["#2b59c3", "#0e8a83", "#d9962a", "#8e44ad", "#c0392b", "#555555"]
for j in range(M):
    ax2[1].bar(t_ms[j::M], volts[j::M], width=enc["theta_s"] * 1000 * 0.9, align="edge",
               color=mask_colors[j % len(mask_colors)], label=f"pulse {j + 1} (× {mask[j]:g})")
ax2[1].axhline(v_limit, color="0.4", ls="--", lw=1)
ax2[1].text(0, v_limit * 1.02, "v_limit: 이보다 높은 pulse는 board가 거부", va="bottom", fontsize=9.5, color="0.35")
ax2[1].set_ylim(0, v_limit * 1.25)
ax2[1].set_xlabel("time (ms)")
ax2[1].set_ylabel("pulse 높이 (V)")
ax2[1].set_title(f"pulse {L * M}개: 칸마다 {M}개, 높이 = {enc['VA']:g} V × u × mask", loc="left")
fig2.tight_layout(rect=(0, 0.08, 1, 1))
fig2.legend(*ax2[1].get_legend_handles_labels(), loc="lower center", ncol=M, bbox_to_anchor=(0.5, 0.0))

plt.show()
