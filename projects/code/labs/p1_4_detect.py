# ============================================================
# P1 실습 4 · 박동 찾기와 채점: 어디까지 줄여도 될까
#
# 전체 과정:
#
#   가짜 심전도 60초 (정답 박동 74개)
#         ↓
#   FS Hz로 집고, BITS bit로 적기 (실습 2 + 실습 3)
#         ↓
#   박동 찾기: 기준선을 빼고, THRESHOLD 선을 넘으면 '박동'
#         ↓
#   정답과 비교: hit · miss · false+ · timing error
#         ↓
#   [그림 1] FS·BITS 한 가지 설정의 판정 결과 (4초 구간)
#   [그림 2] sampling rate 5가지 × bit 5가지 = 25가지 설정의 miss 지도
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

FS = 25             # sampling rate (Hz)
BITS = 3            # bit
THRESHOLD = 0.5     # 판정 선 (mV): 기준선보다 이만큼 높으면 박동
SECONDS = 60
SEED = 1

# 그림 2에서 한꺼번에 볼 설정들
FS_LIST = [25, 50, 100, 250, 500]
BITS_LIST = [3, 4, 6, 8, 12]


# ============================================================
# 2. 가짜 심전도 · 집기 · 적기 (실습 1–3과 같은 코드)
# ============================================================

REF_FS = 2000

def make_ecg(seconds, seed):
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


def digitize(t, x, fs, bits, range_mv=2.0):
    """fs Hz로 집고 bits bit로 반올림해 적는다."""
    step = REF_FS // fs
    ts, xs = t[::step], x[::step]
    lsb = 2 * range_mv / 2 ** bits
    code = np.clip(np.round(xs / lsb), -(2 ** (bits - 1)), 2 ** (bits - 1) - 1)
    return ts, code * lsb


# ============================================================
# 3. 박동 찾기 (detection)
# ============================================================
#
#   ① 기준선 빼기: 0.2초 동안의 평균(= 천천히 흔들리는 기준선)을 뺀다
#   ② 값이 THRESHOLD를 넘으면 → 거기서부터 오르막이 끝나는 꼭대기를 '박동 시각'으로
#   ③ 한 번 찾으면 0.25초 동안은 다시 찾지 않는다
#      (심장은 0.25초 안에 두 번 뛰지 못하므로. 이것을 refractory period라고 함)
# ============================================================

def detect(ts, xq, fs, threshold):
    k = max(1, int(round(0.2 * fs)))
    baseline = np.convolve(xq, np.ones(k) / k, mode="same")     # ① 0.2초 이동평균
    y = xq - baseline
    found, i = [], 0
    while i < len(y):
        if y[i] > threshold:                                     # ② 선을 넘음
            j = i
            while j + 1 < len(y) and y[j + 1] >= y[j]:          #    꼭대기까지 올라가기
                j += 1
            found.append(ts[j])
            i = j + max(1, int(0.25 * fs))                       # ③ 0.25초 쉬기
        else:
            i += 1
    return np.array(found)


# ============================================================
# 4. 채점 (정답과 비교)
# ============================================================
#
#   정답 박동마다 ±50 ms 안에 찾은 박동이 있으면 hit (짝을 지음)
#   짝이 없으면 miss (있는데 못 찾음)
#   짝을 못 지은 찾은 박동은 false+ (없는데 있다고 함)
#   hit의 시각 차이 평균 = timing error
# ============================================================

def score(found, truth, tol=0.05):
    used = np.zeros(len(found), bool)
    hits, errors, missed = [], [], []
    for b in truth:
        d = np.abs(found - b)
        cand = np.where((d <= tol) & ~used)[0]
        if len(cand):
            j = cand[np.argmin(d[cand])]
            used[j] = True
            hits.append(found[j])
            errors.append(abs(found[j] - b))
        else:
            missed.append(b)
    false_pos = found[~used]
    err_ms = 1000 * np.mean(errors) if errors else float("nan")
    return np.array(hits), np.array(missed), false_pos, err_ms


# ============================================================
# 5. 한 가지 설정 (FS, BITS)로 돌리기
# ============================================================

t, ecg, beats = make_ecg(SECONDS, SEED)
ts, xq = digitize(t, ecg, FS, BITS)
found = detect(ts, xq, FS, THRESHOLD)
hits, missed, false_pos, err_ms = score(found, beats)

print("=" * 50)
print(f"{FS} Hz x {BITS} bit  (data rate {FS * BITS} bit/s)")
print("=" * 50)
print(f"true beats    : {len(beats)}")
print(f"hit           : {len(hits)}")
print(f"miss          : {len(missed)}")
print(f"false+        : {len(false_pos)}")
print(f"timing error  : {err_ms:.1f} ms")


# ============================================================
# 6. [그림 1] 판정 결과 보기: 처음 4초
# ============================================================

W = 4.0
m, ms = t < W, ts < W
fig, ax = plt.subplots(figsize=(8, 3.8))
ax.plot(t[m], ecg[m], color="0.8", lw=1.2, label="원래 신호")
ax.step(ts[ms], xq[ms], where="mid", color="#2b59c3", lw=1.3, label=f"{FS} Hz × {BITS} bit")
ax.plot(hits[hits < W], np.full((hits < W).sum(), 1.3), "v", color="#4f7f5d", ms=9, label="hit")
ax.plot(missed[missed < W], np.full((missed < W).sum(), 1.3), "x", color="#c0392b", ms=9, mew=2.5, label="miss")
ax.plot(false_pos[false_pos < W], np.full((false_pos < W).sum(), 1.3), "v", color="#d9962a", ms=9, label="false+")
ax.set_ylim(-0.6, 1.5)
ax.set_xlabel("time (s)")
ax.set_ylabel("mV")
ax.set_title(f"{FS} Hz × {BITS} bit: hit {len(hits)} · miss {len(missed)} · false+ {len(false_pos)} (74개 중)", loc="left")
fig.tight_layout(rect=(0, 0.08, 1, 1))
fig.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=5)


# ============================================================
# 7. [그림 2] 25가지 설정을 한꺼번에: miss 지도
# ============================================================
#
#   가로 = bit, 세로 = sampling rate. 칸 안의 숫자 = miss 개수.
#   진할수록 많이 놓침. 칸 아래 작은 숫자 = data rate (bit/s).
# ============================================================

miss_map = np.zeros((len(FS_LIST), len(BITS_LIST)), int)
print()
print("sampling rate  bit  data rate  hit  miss  false+")
print("   (Hz)              (bit/s)")
print("-------------  ---  ---------  ---  ----  ------")
for i, fs in enumerate(FS_LIST):
    for j, bits in enumerate(BITS_LIST):
        ts_ij, xq_ij = digitize(t, ecg, fs, bits)
        h, mi, fp, _ = score(detect(ts_ij, xq_ij, fs, THRESHOLD), beats)
        miss_map[i, j] = len(mi)
        print(f"     {fs:>3}       {bits:>3}    {fs * bits:>6}    {len(h):>3}   {len(mi):>3}    {len(fp):>3}")

fig2, ax2 = plt.subplots(figsize=(8, 4.6))
ax2.imshow(miss_map, cmap="Reds", vmin=0, vmax=len(beats), aspect="auto")
for i, fs in enumerate(FS_LIST):
    for j, bits in enumerate(BITS_LIST):
        dark = miss_map[i, j] > 35
        ax2.text(j, i - 0.1, f"{miss_map[i, j]}", ha="center", va="center", fontsize=13,
                 fontweight="bold", color="white" if dark else "#2f2521")
        ax2.text(j, i + 0.27, f"{fs * bits:,} bit/s", ha="center", va="center", fontsize=8.5,
                 color="white" if dark else "0.4")
ax2.set_xticks(range(len(BITS_LIST)), [f"{b} bit" for b in BITS_LIST])
ax2.set_yticks(range(len(FS_LIST)), [f"{f} Hz" for f in FS_LIST])
ax2.set_xlabel("bit (값을 얼마나 자세히)")
ax2.set_ylabel("sampling rate (몇 번 집나)")
ax2.set_title("miss 개수 (74개 중). 칸 아래 작은 숫자 = data rate", loc="left")
fig2.tight_layout()

plt.show()   # 그림 창 두 개가 뜹니다. 둘 다 닫으면 끝납니다.
