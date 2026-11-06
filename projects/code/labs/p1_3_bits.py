# ============================================================
# P1 실습 3 · bit: 집은 값을 얼마나 자세히 적을까
#
# 전체 과정:
#
#   가짜 심전도를 촘촘하게(500 Hz) 집기   ← 여기서는 sampling rate 걱정 없이
#         ↓
#   −2 mV ~ +2 mV를 눈금 2^BITS칸으로 나눈 '자' 만들기
#         ↓
#   집은 값을 가장 가까운 눈금으로 반올림 (= 숫자로 적기)
#         ↓
#   그래프: 원래 신호 vs 계단 모양으로 적힌 값
#           특히 작은 물결(P wave, 0.12 mV)이 살아남나?
#
# 맨 위의 BITS 숫자를 3 → 4 → 6 → 12로 바꿔 Run 해 보세요.
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

BITS = 3            # 숫자 하나를 0과 1 몇 자리로 적나. 3, 4, 6, 8, 12 …
FS = 500            # sampling rate는 넉넉하게 고정 (bit 효과만 보려고)
RANGE_MV = 2.0      # 자의 범위: −2 mV ~ +2 mV (폭 4 mV)
SEED = 1


# ============================================================
# 2. 가짜 심전도 만들기 (실습 1·2와 같은 코드)
# ============================================================

REF_FS = 2000

def make_ecg(seconds, seed):
    """가짜 심전도(mV)와 정답 박동 시각(초)을 돌려준다."""
    rng = np.random.default_rng(seed)
    beats, now = [], 0.4
    while now < seconds - 0.6:
        beats.append(now)
        now += 60 / rng.uniform(62, 88)
    t = np.arange(int(seconds * REF_FS)) / REF_FS
    x = np.zeros_like(t)
    for b in beats:
        for shift, height, width in [(-0.18, 0.12, 0.025), (-0.025, -0.12, 0.008), (0, 1.0, 0.009),
                                     (0.025, -0.25, 0.009), (0.28, 0.3, 0.045)]:
            x += height * np.exp(-0.5 * ((t - b - shift) / width) ** 2)
    x += 0.15 * np.sin(2 * np.pi * 0.3 * t) + rng.normal(0, 0.02, t.size)
    return t, x, np.array(beats)

t, ecg, beats = make_ecg(5, SEED)

step = REF_FS // FS
ts, xs = t[::step], ecg[::step]          # 500 Hz로 집은 값


# ============================================================
# 3. '자' 만들기: 눈금 수와 눈금 한 칸(LSB)
# ============================================================
#
#   bit 하나 = 0 또는 1, 두 가지
#   BITS자리  = 2 × 2 × … (BITS번) = 2^BITS 가지 숫자
#   → 폭 4 mV를 2^BITS칸으로 나눈다
#
#   LSB (Least Significant Bit) = 눈금 한 칸의 크기
# ============================================================

levels = 2 ** BITS
lsb = 2 * RANGE_MV / levels               # mV


# ============================================================
# 4. 반올림해서 적기 (quantization)
# ============================================================
#
#   값 ÷ LSB → 가장 가까운 정수로 반올림 → 다시 × LSB
#   예) 3 bit, LSB 0.5 mV:  0.37 mV → 0.74 → 1 → 0.5 mV
#   자의 범위를 넘는 값은 끝 눈금에 붙는다 (clip)
# ============================================================

code = np.round(xs / lsb)
code = np.clip(code, -levels // 2, levels // 2 - 1)
xq = code * lsb


# ============================================================
# 5. P wave가 살아남았나 확인
# ============================================================
#
# P wave = 박동 0.18초 앞의 작은 언덕 (높이 약 0.12 mV).
# 언덕 꼭대기와 그 앞(0.1초 전)의 차이를 원래 값과 적힌 값에서 비교한다.
# ============================================================

def p_height(x_values):
    out = []
    for b in beats[:5]:
        top = x_values[np.argmin(np.abs(ts - (b - 0.18)))]
        before = x_values[np.argmin(np.abs(ts - (b - 0.28)))]
        out.append(top - before)
    return np.mean(out)

print("=" * 50)
print(f"{BITS} bit")
print("=" * 50)
print(f"levels (눈금 수)        : {levels:,}")
print(f"LSB (눈금 한 칸)        : {lsb * 1000:.1f} uV")
print(f"largest rounding error  : {np.abs(xq - xs).max() * 1000:.1f} uV")
print(f"P wave height, original : {p_height(xs) * 1000:.0f} uV")
print(f"P wave height, recorded : {p_height(xq) * 1000:.0f} uV")


# ============================================================
# 6. 그래프: 박동 하나를 크게 (P · R · T가 다 보이게)
# ============================================================

b = beats[1]
m = (ts > b - 0.32) & (ts < b + 0.45)

fig, ax = plt.subplots(figsize=(8, 3.8))

# 눈금선: 이 범위에 들어오는 눈금만 (너무 촘촘하면 생략)
if levels <= 64:
    for k in range(-levels // 2, levels // 2):
        y = k * lsb
        if -0.5 < y < 1.3:
            ax.axhline(y, color="0.9", lw=0.8, zorder=0)

ax.plot((ts[m] - b) * 1000, xs[m], color="0.7", lw=2, label="원래 값")
ax.step((ts[m] - b) * 1000, xq[m], where="mid", color="#2b59c3", lw=1.6, label=f"{BITS} bit로 적은 값")
# P wave 위치에 화살표로 이름표 (데이터와 겹치지 않게 위쪽 빈 곳에서)
ax.annotate("P wave", xy=(-180, 0.25), xytext=(-180, 0.85), ha="center", color="#c0521c",
            fontweight="bold", arrowprops=dict(arrowstyle="->", color="#c0521c"))
ax.set_xlabel("R 봉우리 기준 시간 (ms)")
ax.set_ylabel("mV")
ax.set_ylim(-0.5, 1.3)
ax.set_title(f"{BITS} bit = 눈금 {levels:,}칸, 한 칸(LSB) {lsb * 1000:.0f} µV", loc="left")
fig.tight_layout(rect=(0, 0.08, 1, 1))
fig.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=2)   # 범례는 그래프 아래

plt.show()
