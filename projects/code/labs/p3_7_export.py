# ============================================================
# P3 실습 7 · board가 혼자 판단하도록 파일 내보내기 + 자기 점검 미리 해 보기
#
# 전체 과정:
#
#   실습 6의 판단 식(b_model.joblib) + 실습 5의 측정 조건·state
#         ↓
#   board가 읽는 헤더 파일 네 개 쓰기 (export_mcu.py)
#     config.h       pulse 높이·길이·mask (측정 때와 같게)
#     weights.h      표준화 값 MU·SD, weight W, bias
#     ref_vectors.h  저장된 feature 5개와 Python이 낸 점수 (자기 점검용)
#     inputs_test.h  board가 재생할 시험 입력 24개와 정답
#         ↓
#   board가 켜질 때 하는 자기 점검을 PC에서 먼저 해 보기:
#     헤더 파일의 숫자만으로, board와 같은 순서·같은 float32로 점수 계산
#     → Python 점수와 같은가?
#         ↓
#   [그림] Python 점수 vs board식 점수, weight가 큰 pulse
# ============================================================

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

import joblib
import export_mcu                                   # 헤더 쓰기·다시 읽기·board식 점수 계산
from common import load_json


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

MOCK = True          # True: mock 결과로 연습 / False: 진짜 측정 결과 → firmware/B6_standalone에 씀

CONFIG = "config_board_example.json" if MOCK else "config_board.json"
BASE = CODE / "runs" / ("p3_mock" if MOCK else "p3")
RUN_DIR = BASE / "b_dev01"
MODEL_PATH = BASE / "b_model.joblib"
OUT_DIR = BASE / "B6_standalone" if MOCK else CODE / "firmware" / "B6_standalone"


# ============================================================
# 2. 읽기: 판단 식, 측정 조건(manifest), state, 입력
# ============================================================

pack = joblib.load(MODEL_PATH)
model = pack["model"]
cols = None if not pack["cols"] else [int(c) for c in pack["cols"].split(",")]   # 쓴 feature 열 번호
manifest = load_json(RUN_DIR / "manifest.json")    # 측정 때의 pulse 높이·mask 등
v_limit = load_json(CODE / "python" / CONFIG)["instrument"]["v_limit_V"]

ck = np.load(RUN_DIR / "checkpoint.npz")
F = ck["S"][ck["done"]]
if cols is not None:
    F = F[:, cols]
task = np.load(BASE / "task.npz")


# ============================================================
# 3. 헤더 파일 네 개 쓰기
# ============================================================
#
#   네 파일은 '같은 학습'에서 함께 나와야 한다. 하나만 바꾸면 자기 점검이 FAIL.
# ============================================================

info = export_mcu.export(model, manifest, F, str(OUT_DIR), v_limit, cols=cols)
te = task["test_idx"]
export_mcu.export_inputs(task["U"][te], task["y"][te], str(OUT_DIR))

print(f"L = {info['L']}, M = {info['M']}, features NF = {info['NF']}, scores NC = {info['NC']}")
print(f"written to {OUT_DIR.relative_to(CODE).as_posix()}/")
for name in ("config.h", "weights.h", "ref_vectors.h", "inputs_test.h"):
    print(f"   {name:<14} {(OUT_DIR / name).stat().st_size:>6} bytes")


# ============================================================
# 4. 자기 점검을 PC에서: 헤더 숫자만으로 board처럼 계산
# ============================================================
#
#   board 계산 (B6_standalone의 scores 함수와 같은 순서):
#     z = (feature − MU) / SD          ← 표준화
#     점수 = BIAS + Σ W × z              ← float32 (board의 float)
#   Python 계산: model.decision_function (float64)
#   두 점수의 차이가 상대 0.001보다 작으면 board는 FAIL을 찍지 않는다.
# ============================================================

h = export_mcu.read_header_arrays(OUT_DIR / "weights.h")
h.update(export_mcu.read_header_arrays(OUT_DIR / "ref_vectors.h"))
XREF = h["XREF"].reshape(-1, info["NF"])
SREF = h["SREF"]

print()
print("self-check, as the board prints it: R,row,score#,board,python")
fails = 0
for r, x in enumerate(XREF):
    board = float(export_mcu.mcu_score(x, h)[0])
    python = float(SREF[r])
    bad = abs(board - python) > 1e-3 * (1 + abs(python))
    fails += bad
    print(f"R,{r},0,{board:.6f},{python:.6f}{',FAIL' if bad else ''}")

board_all = np.array([export_mcu.mcu_score(x, h)[0] for x in F])
python_all = model.decision_function(F)
print(f"\nall {len(F)} stored trials: largest |board - python| = {np.max(np.abs(board_all - python_all)):.1e}")
print("self-check:", "FAIL" if fails else "OK (no FAIL)")


# ============================================================
# 5. 그림: 점수 비교 + weight
# ============================================================

fig, ax = plt.subplots(1, 2, figsize=(8, 3.8), gridspec_kw={"width_ratios": [1, 1.5]})

lim = np.abs(python_all).max() * 1.1
ax[0].plot([-lim, lim], [-lim, lim], color="0.75", lw=1)
ax[0].plot(python_all, board_all, "o", color="#2b59c3", ms=4, alpha=0.7)
ax[0].plot(SREF, [export_mcu.mcu_score(x, h)[0] for x in XREF], "s", color="#c0392b", ms=7,
           mfc="none", mew=1.5, label="자기 점검 5개")
ax[0].set_xlabel("Python 점수")
ax[0].set_ylabel("board식 점수 (float32)")
ax[0].set_title("두 계산이 한 줄 위에", loc="left")
ax[0].legend(loc="upper left", fontsize=9.5)

W = h["W"]
labels = [f"{c // info['M']}-{c % info['M'] + 1}" for c in (cols if cols is not None else range(info["NF"]))]
ax[1].bar(range(len(W)), W, color=np.where(W > 0, "#d9962a", "#2b59c3"))
ax[1].axhline(0, color="0.5", lw=0.8)
ax[1].set_xticks(range(len(W)), labels, rotation=90, fontsize=9)
ax[1].set_xlabel("feature (칸-pulse)")
ax[1].set_ylabel("weight")
ax[1].set_title("weight: 주황 + 는 class 1 쪽으로", loc="left")

fig.tight_layout()
plt.show()
