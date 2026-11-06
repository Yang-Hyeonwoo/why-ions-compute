# ============================================================
# P4 실습 5 · tapper 시험: 리듬 한 번 누르고 힘 곡선 보기
#
# 전체 과정:
#
#   tapper board에 "T,번호,간격,간격,간격" 한 줄 보내기 (4번 눌러라)
#         ↓
#   board가 돌려주는 네 줄 읽기
#     O  : 실제 onset 시각 4개 (ms)
#     FT : 힘을 잰 시각들 (ms, 80 SPS면 12.5 ms 간격)
#     FV : 그 시각의 힘 (N)
#     X  : 마지막 onset 시각 = '끝' trigger
#         ↓
#   누름마다 peak force(가장 큰 힘)와 hold(최대의 절반을 넘은 시간)
#         ↓
#   REPEAT번 되풀이 → 그림 1: 힘 곡선,  그림 2(REPEAT > 1): 매번의 peak force 흩어짐
#
# MOCK = True  : board 없이 컴퓨터가 만든 가짜 힘 곡선 (지금 바로 돌려 볼 수 있음)
# MOCK = False : 진짜 tapper (C_tapper firmware, TARE·calibration 끝낸 뒤) [실물 미검증]
# ============================================================

import sys
import time
from pathlib import Path

# 공용 코드(python 폴더)를 불러오려고 경로를 잡는다.
CODE = Path(__file__).resolve().parent.parent      # ion-projects-code 폴더
sys.path.insert(0, str(CODE / "python"))           # 공용 코드 폴더를 찾을 수 있게

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

MOCK = True                  # True: board 없이 연습,  False: 진짜 tapper
PORT = "COM6"                # tapper board의 COM 번호 (장치 관리자에서 확인). MOCK = False일 때만 씀
GAPS_MS = [600, 600, 600]    # onset 간격 3개 (ms). firmware 한계: 150–5000
REPEAT = 1                   # 같은 리듬을 몇 번 누를까 (흩어짐을 보려면 50)


# ============================================================
# 2. tapper에 한 번 누르라고 하기
# ============================================================
#
#   보내는 글자:  T,1,600,600,600   (Serial Monitor에 손으로 치던 것과 같음)
#   받는 글자:    O,1,…   FT,1,…   FV,1,…   X,1,…
#   글자를 쉼표로 잘라 숫자 목록으로 바꾼다.
# ============================================================

if MOCK:
    from c_mock import simulate                    # 공용 코드: 가짜 힘 곡선 (80 ms 반달 모양)

    def tap_once(n, gaps_ms):
        rng = np.random.default_rng(n)
        t, I, onsets, tf, F = simulate(np.array(gaps_ms) / 1000, rng, "memoryless", dict(force=1.0, base=1.0))
        return {"O": onsets * 1000, "FT": tf * 1000, "FV": F, "X": [onsets[-1] * 1000]}
else:
    import serial                                  # USB로 board와 글자를 주고받는 도구 (pyserial)
    ser = serial.Serial(PORT, 115200, timeout=15)  # Serial Monitor가 열려 있으면 여기서 오류
    time.sleep(2)                                  # board가 연결을 받을 때까지 잠깐 기다림
    ser.reset_input_buffer()

    def tap_once(n, gaps_ms):
        ser.write(("T,%d,%d,%d,%d\n" % (n, *gaps_ms)).encode())
        got = {}
        while "X" not in got:                      # X 줄이 오면 한 번 끝
            line = ser.readline().decode(errors="replace").strip()
            if not line:
                raise TimeoutError(f"trial {n}: no answer from tapper")
            p = line.split(",")
            if p[0] == "E":
                raise RuntimeError(f"trial {n}: tapper rejected {line}")
            if len(p) > 1 and p[1] == str(n):
                got[p[0]] = np.array([float(v) for v in p[2:]])
        return got


# ============================================================
# 3. 누름마다 peak force · hold
# ============================================================
#
#   각 onset부터 0.12초 안(누름 80 ms + 여유)에서
#     peak = 가장 큰 힘,   hold = 힘이 peak의 절반을 넘은 시간
# ============================================================

def press_stats(rec):
    tf, F = np.asarray(rec["FT"]) / 1000, np.asarray(rec["FV"])
    peaks, holds = [], []
    for o in np.asarray(rec["O"]) / 1000:
        m = (tf >= o - 0.02) & (tf < o + 0.12)
        pk = F[m].max()
        above = tf[m][F[m] > 0.5 * pk]
        peaks.append(pk)
        holds.append((above[-1] - above[0]) * 1000 if len(above) > 1 else np.nan)
    return np.array(peaks), np.array(holds)


records = []
for n in range(1, REPEAT + 1):
    rec = tap_once(n, GAPS_MS)
    records.append((rec, *press_stats(rec)))
if not MOCK:
    ser.close()


# ============================================================
# 4. 숫자로 확인
# ============================================================

print("=" * 60)
print(f"tapper test: T,n,{','.join(map(str, GAPS_MS))}  x {REPEAT}   ({'MOCK, no board' if MOCK else PORT})")
print("=" * 60)
print("trial  onsets (ms)              peak force (N)            hold (ms)")
for n, (rec, pk, hd) in enumerate(records[:5], 1):
    on = " ".join(f"{o:.0f}" for o in rec["O"])
    print(f"{n:<5}  {on:<23}  {' '.join(f'{p:.2f}' for p in pk):<24}  {' '.join(f'{h:.0f}' for h in hd)}")
if REPEAT > 5:
    print(f"...    ({REPEAT - 5} more)")
allpk = np.concatenate([pk for _, pk, _ in records])
allhd = np.concatenate([hd for _, _, hd in records])
print()
print(f"peak force : mean {allpk.mean():.2f} N, SD {allpk.std():.2f} N  ({len(allpk)} presses)")
print(f"hold       : mean {np.nanmean(allhd):.0f} ms, SD {np.nanstd(allhd):.0f} ms")
print(f"last onset (X trigger) of trial 1: {records[0][0]['X'][0]:.0f} ms")


# ============================================================
# 5. 그림 1: 첫 번째 누름 기록의 힘 곡선
# ============================================================

rec, pk, hd = records[0]
tf, F, on = np.asarray(rec["FT"]) / 1000, np.asarray(rec["FV"]), np.asarray(rec["O"]) / 1000
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.plot(tf, F, ".-", color="#c0392b", lw=1.4, ms=4, label="load cell 힘 (점 = 12.5 ms마다 한 번 잰 값)")
for k, o in enumerate(on):
    ax.axvline(o, color="#2b59c3", ls="--", lw=1, label="onset (O 줄)" if k == 0 else None)
    ax.text(o + 0.1, pk[k], f"{pk[k]:.2f} N", va="center", color="#c0392b", fontsize=10)
ax.axvline(rec["X"][0] / 1000, color="#7a3db8", lw=2, alpha=0.4, label="X: 마지막 onset ('끝')")
ax.set_xlabel("명령을 받은 순간부터의 시간 (s)")
ax.set_ylabel("force (N)")
ax.set_ylim(-0.1, max(pk) * 1.25)
ax.set_title(f"tapper 한 번: T,1,{','.join(map(str, GAPS_MS))}  ({'MOCK' if MOCK else '실물'})", loc="left")
fig.tight_layout(rect=(0, 0.1, 1, 1))
fig.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=3, fontsize=9.5)


# ============================================================
# 6. 그림 2: REPEAT번의 peak force 흩어짐 (REPEAT > 1일 때만)
# ============================================================

if REPEAT > 1:
    fig2, ax = plt.subplots(figsize=(8, 3.6))
    for k in range(4):
        ax.plot(range(1, REPEAT + 1), [r[1][k] for r in records], "o", ms=4, alpha=0.7, label=f"{k + 1}번째 누름")
    ax.axhspan(allpk.mean() - allpk.std(), allpk.mean() + allpk.std(), color="0.85", lw=0,
               label=f"평균 ± SD ({allpk.mean():.2f} ± {allpk.std():.2f} N)")
    ax.set_xlabel("trial 번호")
    ax.set_ylabel("peak force (N)")
    ax.set_title(f"같은 리듬 {REPEAT}번: 매번 같은 힘으로 눌렀나?", loc="left")
    fig2.tight_layout(rect=(0, 0.1, 1, 1))
    fig2.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=5, fontsize=9.5)

plt.show()   # 그림 창이 뜹니다. 창을 닫으면 프로그램이 끝납니다.
