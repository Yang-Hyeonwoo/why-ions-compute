# ============================================================
# P3 실습 1 · 버튼 리듬을 CSV로 남기기
#
# 전체 과정:
#
#   board(B1a_rhythm)가 5 ms마다 한 줄씩 보낸다:  n,t_ms,btn,a0
#         ↓
#   PC가 SECONDS초 동안 그 줄을 받는다
#   (MOCK = True면 board 대신 컴퓨터 속 '가짜 board'가 줄을 만든다)
#         ↓
#   줄을 숫자로 나누기 → 빠진 줄·누름·접점 튐(bounce) 세기
#         ↓
#   CSV 파일에 저장 + 그림: 내가 친 리듬이 계단 모양으로 보인다
#
# 처음에는 MOCK = True로 board 없이 돌려 봅니다.
# board에 B1a_rhythm을 올린 뒤에는 MOCK = False, PORT = 내 COM 번호.
# ============================================================

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

# 공용 코드(python 폴더)를 쓸 수 있게 경로를 잡는다.
# 이 파일은 ion-projects-code/mylabs/ 안에 있으므로, 한 칸 위가 ion-projects-code 폴더.
CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

import b1_record      # board 줄 읽기·CSV 저장 (P3.1a 공용 코드)
import b1_memory      # 가짜 리듬 만들기 (MOCK일 때만 씀)


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

MOCK = True        # True: board 없이 가짜 board로 / False: 진짜 board에서 받기
PORT = "COM5"      # 진짜 board의 COM 번호 (장치 관리자에서 본 번호)
LABEL = "X"        # 이번 기록에서 친 리듬 이름: "X" 또는 "Y"
SESSION = "s1"     # 몇 번째 회차: "s1", "s2", "s3" …
SECONDS = 40       # 몇 초 동안 받을까

MOCK_DROP = 0      # (가짜 board만) PC가 줄을 놓친 구간을 몇 군데 만들까. 0, 1, 2 …


# ============================================================
# 2. 줄 받기
# ============================================================
#
# board가 보내는 한 줄 = "n,t_ms,btn,a0"
#   n    : 줄 번호 (0, 1, 2 …). 하나씩 늘어야 정상. 건너뛰면 그 사이 줄을 놓친 것
#   t_ms : board가 켜진 뒤 지난 시간 (ms)
#   btn  : 버튼 1 = 눌림, 0 = 뗌
#   a0   : 빛 센서 값 (0–4095). 센서를 안 꽂았으면 아무 값
# ============================================================

FS = 200   # board는 1초에 200줄 (5 ms마다 한 줄)


def mock_board_lines(label, seconds, n_drop, seed=3):
    """가짜 board: 사람이 리듬을 친 것처럼 '200 Hz 줄'을 만든다 (실측 아님)."""
    rng = np.random.default_rng(seed)
    n_rhythms = int(seconds / 4.5) + 1              # 리듬 한 번 + 쉼 ≈ 4.5초 (넉넉히 만들고 SECONDS에서 자름)
    t, btn, light = b1_memory.synth_stream(label, n_rhythms, rng)
    keep = t < seconds
    lines = [f"{i},{3061 + round(t[i] * 1000)},{btn[i]},{int(light[i] / 3.6 * 4095)}"
             for i in np.where(keep)[0]]
    for _ in range(n_drop):                          # PC가 바빠 줄 20개(0.1초)를 못 받은 것처럼
        k = rng.integers(200, len(lines) - 200)
        del lines[k:k + 20]
    return lines


if MOCK:
    lines = mock_board_lines(LABEL, SECONDS, MOCK_DROP)
    rows = [r for r in (b1_record.parse(x) for x in lines) if r]
    print(f"(MOCK) fake board, {SECONDS} s")
    print("first 3 lines from the board:")
    for x in lines[:3]:
        print("   ", x)
else:
    print(f"recording {SECONDS} s from {PORT} ... tap button 1 now")
    rows = b1_record.record(PORT, SECONDS)            # 진짜 board에서 SECONDS초 동안 받기
    if not rows:
        raise SystemExit("받은 줄이 없습니다. COM 번호, Serial Monitor가 닫혔는지, B1a_rhythm이 올라갔는지 확인하세요.")

# b1_record.parse가 한 줄을 (n, 시각 s, 버튼, 빛 V)로 바꿔 둔다
n_col = np.array([r[0] for r in rows])
t = np.array([r[1] for r in rows])
t = t - t[0]                                       # 기록 시작을 0초로
btn = np.array([r[2] for r in rows])
light = np.array([r[3] for r in rows])


# ============================================================
# 3. 세기: 빠진 줄 · 누름 · 접점 튐 · 빛 포화
# ============================================================

# 빠진 줄: 줄 번호 n이 1씩 늘지 않은 곳
gaps = int(np.sum(np.diff(n_col) != 1))

# 누름 = 버튼이 0 → 1로 바뀐 순간, 뗌 = 1 → 0
press_t = t[1:][(btn[1:] == 1) & (btn[:-1] == 0)]
release_t = t[1:][(btn[1:] == 0) & (btn[:-1] == 1)]

# 접점 튐(bounce): 뗀 지 30 ms 안에 다시 눌린 것 → 진짜 누름이 아니다
bounce_t = [p for p in press_t if np.any((p - release_t >= 0) & (p - release_t < 0.03))]
real_press_t = [p for p in press_t if p not in bounce_t]

# 빛 포화: 빛 값이 0 V나 3.6 V 끝에 붙은 줄 (센서를 안 꽂았으면 무시)
saturated = int(np.sum((light > 3.6 * 0.98) | (light < 0.02)))

if not real_press_t:
    raise SystemExit("누름이 하나도 없습니다. 버튼1을 눌렀는지, B1a_rhythm이 올라갔는지 확인하세요.")

print()
print(f"lines received        : {len(rows)}   (expected about {SECONDS * FS})")
print(f"dropped gaps          : {gaps}")
print(f"presses (0 -> 1)      : {len(press_t)}")
print(f"  bounces (< 30 ms)   : {len(bounce_t)}")
print(f"  real presses        : {len(real_press_t)}")
print(f"light saturated lines : {saturated}")


# ============================================================
# 4. CSV로 저장
# ============================================================
#
# 진짜 기록은 runs/p3/b1_taps.csv 한 파일에 계속 이어 붙인다 (session·label 열로 구별).
# 가짜 기록은 runs/p3_mock/b1_taps.csv에 매번 새로 쓴다 (진짜 기록과 섞이지 않게).
# ============================================================

out = CODE / "runs" / ("p3_mock" if MOCK else "p3") / "b1_taps.csv"
out.parent.mkdir(parents=True, exist_ok=True)
if MOCK and out.exists():
    out.unlink()
b1_record.append_csv(str(out), SESSION, LABEL, rows)
print(f"\nCSV: runs/{out.parent.name}/{out.name}  (session {SESSION}, label {LABEL})")


# ============================================================
# 5. 그림: 위 = 전체 기록, 아래 = 리듬 하나 크게
# ============================================================

fig, ax = plt.subplots(2, 1, figsize=(8, 5.4), gridspec_kw={"height_ratios": [1, 1.3]})

ax[0].step(t, btn, where="post", color="#2b59c3", lw=1)
ax[0].set_yticks([0, 1], ["뗌 0", "눌림 1"])
ax[0].set_xlabel("time (s)")
ax[0].set_title(f"전체 {t[-1]:.0f}초: 리듬 '{LABEL}'을 친 묶음이 보인다", loc="left")
# 빠진 줄이 있으면 그 자리를 빨간 띠로 (0.1초는 너무 가늘어서 앞뒤로 0.3초씩 넓혀 칠함)
for k in np.where(np.diff(n_col) != 1)[0]:
    ax[0].axvspan(t[k] - 0.3, t[k + 1] + 0.3, color="#c0392b", alpha=0.3, lw=0)

# 아래: 리듬 하나 크게. bounce가 있으면 그 bounce가 든 리듬을 고른다
starts = [p for i, p in enumerate(real_press_t) if i == 0 or p - real_press_t[i - 1] > 1.6]   # 리듬마다 첫 누름
pick = starts[0]
if bounce_t:
    pick = max(s for s in starts if s <= bounce_t[0])
t0 = pick - 0.2
z = (t >= t0) & (t <= t0 + 2.6)
ax[1].step((t[z] - t0) * 1000, btn[z], where="post", color="#2b59c3", lw=1.2, label="버튼 (5 ms마다 한 줄)")
rp = [p for p in real_press_t if t0 <= p <= t0 + 2.6]
bp = [p for p in bounce_t if t0 <= p <= t0 + 2.6]
ax[1].plot((np.array(rp) - t0) * 1000, np.full(len(rp), 1.15), "v", color="#0e8a83", ms=8, label="누름으로 셈")
if bp:
    ax[1].plot((np.array(bp) - t0) * 1000, np.full(len(bp), 1.15), "x", color="#c0392b", ms=9, mew=2,
               label="bounce로 버림")
ax[1].set_ylim(-0.1, 1.3)
ax[1].set_yticks([0, 1], ["뗌 0", "눌림 1"])
ax[1].set_xlabel("이 리듬의 첫 누름 0.2초 전부터 (ms)")
ax[1].set_title("리듬 하나 크게: ▼ 하나가 누름 하나", loc="left")

fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.legend(*ax[1].get_legend_handles_labels(), loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.0))

plt.show()   # 그림 창을 닫으면 프로그램이 끝납니다
