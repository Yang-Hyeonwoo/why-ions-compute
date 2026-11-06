# ============================================================
# P4 실습 3 · easy cue 점검: 리듬마다 누른 힘·누름 시간이 달랐나
#
# 전체 과정:
#
#   실습 2의 기록 폴더 읽기 (runs/c_mock_memory_day1, …_day2)
#         ↓
#   trial마다 load cell 힘 기록에서 세 숫자 뽑기
#     peak force : 누름 4번 각각의 가장 큰 힘 → 평균 (N)
#     hold       : 힘이 그 누름 최대의 절반을 넘은 시간 → 평균 (ms)
#     span       : 첫 onset → 마지막 onset (s)
#         ↓
#   같은 날 안에서 리듬 4개끼리 견주기 (평균 ± SD)
#         ↓
#   그림: 리듬마다 trial 하나 = 점 하나
#
# 왜? 리듬마다 힘이 달랐다면, 소자가 기억하지 않아도 '힘'만 보고 리듬을 맞힐 수 있다.
#     그런 엉뚱한 힌트(easy cue)가 없는지 먼저 본다. 전류는 아직 보지 않는다.
# ============================================================

import sys
from pathlib import Path

# 공용 코드(python 폴더)를 불러오려고 경로를 잡는다.
CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

import numpy as np
import matplotlib.pyplot as plt
from c_analyze import load_session                 # 공용 코드: 기록 폴더 하나 읽기 (실물 분석과 같음)
from common import print_table                     # 공용 코드: TERMINAL에 표 찍기


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

# 분석할 기록 폴더 (runs 안). 실물 기록이면 예: ["c_dev01_day1"]
RUNS = ["c_mock_memory_day1", "c_mock_memory_day2"]


# ============================================================
# 2. 기록 읽기
# ============================================================
#
#   load_session은 폴더 안의 trial 파일(raw/trial_00000.npz …)을 하나씩 열어
#   trial마다 { y(리듬 번호), peak, hold, span, 그리고 실습 4가 쓸 전류 숫자들 }을 만든다.
# ============================================================

sessions = {name: load_session(str(CODE / "runs" / name)) for name in RUNS}
NAMES_KO = ["R1 고르게", "R2 앞에 몰림", "R3 뒤에 몰림", "R4 가운데 쉼"]


def values(rows, key, rhythm, scale=1.0):
    """한 날(rows)에서 그 리듬 trial들의 key 값 목록"""
    return np.array([r[key] for r in rows if r["y"] == rhythm]) * scale


# ============================================================
# 3. 표: 리듬마다 평균 +/- SD
# ============================================================
#
#   SD(표준편차) = 값들이 평균에서 보통 얼마나 벗어나나.
#   리듬끼리의 평균 차이가 각자의 SD보다 작으면 → 힘으로는 리듬을 가릴 수 없다 (좋음).
# ============================================================

rows_t = []
for name, rows in sessions.items():
    for c in range(4):
        cells = []
        for key, scale, fmt in (("peak", 1, ".2f"), ("hold", 1000, ".1f"), ("span", 1, ".2f")):
            v = values(rows, key, c, scale)
            cells.append(f"{np.nanmean(v):{fmt}} +/- {np.nanstd(v):{fmt}}")
        rows_t.append([name, f"R{c + 1}"] + cells)

print("Easy-cue check (mean +/- SD per rhythm)")
print_table(["session", "rhythm", "peak force (N)", "hold (ms)", "span (s)"], rows_t, left=(0,))
print()
for name, rows in sessions.items():
    means = [np.nanmean(values(rows, "peak", c)) for c in range(4)]
    sds = [np.nanstd(values(rows, "peak", c)) for c in range(4)]
    print(f"{name}: peak force spread between rhythms {max(means) - min(means):.3f} N, "
          f"typical SD within a rhythm {np.mean(sds):.3f} N")


# ============================================================
# 4. 그림: 세 칸 (peak force · hold · span). 점 하나 = trial 하나
# ============================================================

fig, axes = plt.subplots(1, 3, figsize=(8, 4.0))
marks = ["o", "s", "^", "D"]
for ax, (key, scale, label) in zip(axes, (("peak", 1, "peak force (N)"),
                                          ("hold", 1000, "hold (ms)"),
                                          ("span", 1, "span (s)"))):
    for k, (name, rows) in enumerate(sessions.items()):
        for c in range(4):
            v = values(rows, key, c, scale)
            xc = c + (k - (len(sessions) - 1) / 2) * 0.3            # 날마다 조금 옆으로 비켜 놓기
            x = xc + np.random.default_rng(c).uniform(-0.07, 0.07, len(v))   # 점이 겹치지 않게 살짝 흩기
            ax.plot(x, v, marks[k % 4], ms=4, alpha=0.55, color=f"C{k}",
                    label=name if (c == 0 and ax is axes[0]) else None)
            ax.plot([xc - 0.12, xc + 0.12], [np.nanmean(v)] * 2, color="black", lw=2)   # 평균
    ax.set_xticks(range(4), ["R1", "R2", "R3", "R4"])
    ax.set_title(label, loc="left", fontsize=11)
axes[2].set_ylim(1.7, 1.9)            # span은 모두 1.8초
axes[2].set_yticks([1.7, 1.8, 1.9])
fig.suptitle("리듬마다 누른 방식이 같았나? (검은 가로선 = 평균)", x=0.02, ha="left", fontsize=12)
fig.tight_layout(rect=(0, 0.08, 1, 1))
fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=len(sessions))

plt.show()   # 그림 창이 뜹니다. 창을 닫으면 프로그램이 끝납니다.
