# ============================================================
# P1 실습 1 · 가짜 심전도(synthetic ECG) 만들고 보기
#
# 전체 과정:
#
#   심장이 뛰는 시각 정하기 (1분에 62–88번)
#         ↓
#   박동마다 P · Q · R · S · T 물결을 더하기
#         ↓
#   숨 쉴 때 흔들리는 기준선 + 작은 noise 더하기
#         ↓
#   그래프로 보기
#
# 이 신호는 진짜 환자 기록이 아니라 수식으로 그린 것입니다.
# 그래서 "심장이 언제 뛰었는지(정답)"를 우리가 정확히 압니다.
# 다음 실습들은 이 정답을 기준으로 채점합니다.
# ============================================================

import numpy as np
import matplotlib.pyplot as plt


# ============================================================
# 0. 그림 설정 (한글 글꼴 · 글씨 크기) — 건드리지 않아도 됩니다
# ============================================================

plt.rcParams.update({
    "font.family": "Malgun Gothic",   # Windows 기본 한글 글꼴
    "axes.unicode_minus": False,      # 마이너스(-)가 깨지지 않게
    "font.size": 11,
    "legend.frameon": False,          # 범례 테두리 없음
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# ============================================================
# 1. 바꿔 볼 수 있는 설정값
# ============================================================

SECONDS = 10      # 신호 길이 (초)
SEED = 1          # 무작위 '씨앗'. 같은 SEED면 언제 돌려도 같은 신호
SHOW_SECONDS = 3  # 그래프에 보여 줄 앞부분 길이 (초)


# 컴퓨터 안에서 "원래 신호"를 그리는 촘촘함.
# 1초에 2000개 점 = 0.5 ms마다 점 하나 → 사람 눈에는 매끈한 곡선.
REF_FS = 2000


# ============================================================
# 2. 심장이 뛰는 시각 정하기
# ============================================================

rng = np.random.default_rng(SEED)

beat_times = []        # 정답: 심장이 뛴 시각 (초)
now = 0.4              # 첫 박동은 0.4초에

while now < SECONDS - 0.6:
    beat_times.append(now)

    # 다음 박동까지의 간격.
    # 1분에 62–88번 뛰므로 간격은 60/88 ≈ 0.68초 ~ 60/62 ≈ 0.97초.
    beats_per_minute = rng.uniform(62, 88)
    now += 60 / beats_per_minute

beat_times = np.array(beat_times)


# ============================================================
# 3. 박동마다 물결 다섯 개(P, Q, R, S, T) 더하기
# ============================================================
#
#   P: 작은 언덕 (심방이 수축)        높이 0.12 mV
#   Q: 작은 골짜기                    -0.12 mV
#   R: 크고 뾰족한 봉우리 (심실 수축)  1.0 mV   ← 박동 찾기에 쓰는 것
#   S: 골짜기                         -0.25 mV
#   T: 넓은 언덕 (회복)               0.3 mV
#
# 물결 하나 = 종 모양(가우스) 곡선.
#   (박동 기준 몇 초 뒤, 높이 mV, 폭 초)
# ============================================================

WAVES = [
    (-0.180,  0.12, 0.025),   # P
    (-0.025, -0.12, 0.008),   # Q
    ( 0.000,  1.00, 0.009),   # R
    ( 0.025, -0.25, 0.009),   # S
    ( 0.280,  0.30, 0.045),   # T
]

t = np.arange(int(SECONDS * REF_FS)) / REF_FS   # 시간 축 (초)
ecg = np.zeros_like(t)                          # 처음엔 0 mV

for b in beat_times:
    for shift, height, width in WAVES:
        ecg += height * np.exp(-0.5 * ((t - b - shift) / width) ** 2)


# ============================================================
# 4. 실제 신호처럼 흔들림 더하기
# ============================================================

# 숨 쉴 때 몸이 움직여 기준선이 천천히 오르내림 (0.3 Hz = 3.3초에 한 번)
ecg += 0.15 * np.sin(2 * np.pi * 0.3 * t)

# 전극·근육에서 오는 작은 noise (표준편차 0.02 mV)
ecg += rng.normal(0, 0.02, t.size)


# ============================================================
# 5. 숫자로 확인
# ============================================================

print("=" * 50)
print("synthetic ECG")
print("=" * 50)
print(f"length          : {SECONDS} s")
print(f"points          : {t.size} (1초에 {REF_FS}개)")
print(f"true beats      : {len(beat_times)}")
print(f"heart rate      : {len(beat_times) / SECONDS * 60:.0f} beats/min")
print(f"first 3 beats   : {np.round(beat_times[:3], 3)} s")
print(f"min / max value : {ecg.min():.2f} / {ecg.max():.2f} mV")


# ============================================================
# 6. 그래프: 앞부분 SHOW_SECONDS초
# ============================================================

show = t < SHOW_SECONDS

fig, ax = plt.subplots(figsize=(8, 3.6))
ax.plot(t[show], ecg[show], color="0.35", lw=1.2, label="synthetic ECG")

# 정답 박동 시각에 빨간 ▼ (R 봉우리 위)
b_show = beat_times[beat_times < SHOW_SECONDS]
ax.plot(b_show, np.full(len(b_show), 1.25), "v", color="#c0392b", ms=8,
        label="정답: 심장이 뛴 시각")

# 첫 박동의 물결 이름 붙이기
b0 = beat_times[0]
# 글자는 실제 신호 높이에서 조금 위(+) 또는 아래(−)에 둔다 (기준선이 흔들려도 맞게)
LABEL_AT = {"P": (-0.18, +0.10), "Q": (-0.03, -0.20), "R": (0.012, -0.12),
            "S": (0.03, -0.18), "T": (0.28, +0.10)}   # (박동 기준 몇 초, 위아래 띄우기 mV)
for name, (dx, dy) in LABEL_AT.items():
    y = ecg[int((b0 + dx) * REF_FS)] + dy
    ax.text(b0 + dx + (0.015 if name == "R" else 0), y, name, ha="left" if name == "R" else "center",
            va="bottom" if dy > 0 else "top", color="#2b59c3", fontweight="bold")

ax.set_ylim(-0.6, 1.55)
ax.set_xlabel("time (s)")
ax.set_ylabel("mV")
ax.set_title("가짜 심전도: 박동마다 P·Q·R·S·T 물결", loc="left")
ax.legend(loc="upper right", ncol=2, bbox_to_anchor=(1.0, 1.16))
fig.tight_layout()

plt.show()   # 그림 창이 뜹니다. 창을 닫으면 프로그램이 끝납니다.
