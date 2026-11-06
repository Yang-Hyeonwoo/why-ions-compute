# ============================================================
# 첫 실습 · VS Code에서 코드 돌려 보기
#
# 전체 과정:
#
#   숫자 몇 개 계산해서 글자로 찍기 (print)  → 아래 TERMINAL에 보임
#         ↓
#   사인(sin) 곡선 그리기 (plot)            → 그림 창이 따로 뜸
#
# 이 파일이 잘 돌면 준비 끝입니다.
# ============================================================

import sys                         # 지금 실행 중인 Python의 정보
import numpy as np                 # 숫자 계산 도구
import matplotlib.pyplot as plt    # 그래프 도구


# ============================================================
# 0. 그림 설정 (한글 글꼴) — 모든 실습 파일 맨 위에 똑같이 있습니다
# ============================================================

plt.rcParams.update({
    "font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 11,
    "legend.frameon": False, "axes.spines.top": False, "axes.spines.right": False,
})


# ============================================================
# 1. 바꿔 볼 수 있는 설정값
# ============================================================

FREQ = 2.0      # 1초에 몇 번 오르내리나 (Hz)


# ============================================================
# 2. 계산하고 글자로 찍기
# ============================================================

t = np.linspace(0, 1, 500)               # 0초부터 1초까지 점 500개
y = np.sin(2 * np.pi * FREQ * t)         # 사인 곡선

print("hello! VS Code에서 Python이 돌아갑니다.")
print(f"python : {sys.executable} ({sys.version.split()[0]})")   # p0_install.py가 찍은 줄과 같아야 함
print(f"points : {len(t)}")
print(f"FREQ   : {FREQ} Hz  → 1초 동안 {FREQ:g}번 오르내림")
print(f"max    : {y.max():.2f}")


# ============================================================
# 3. 그림 그리기
# ============================================================

fig, ax = plt.subplots(figsize=(8, 3.2))
ax.plot(t, y, color="#2b59c3", lw=2)
ax.set_xlabel("time (s)")
ax.set_ylabel("value")
ax.set_title(f"FREQ = {FREQ:g} Hz 사인 곡선", loc="left")
fig.tight_layout()

plt.show()   # 그림 창이 뜹니다. 창을 닫으면 프로그램이 끝납니다.
