"""C: 두드림 리듬 과제의 일정 만들기와 '끝에서 읽기' 특징 뽑기.

시간 용어 (그림 ⑥과 같음)
  onset 간격  = 한 누름의 시작 → 다음 누름의 시작
  누름 시간   = HOLD (서보가 내려가 있는 시간, 실제 접촉 시간은 force 기록으로 확인)
  총 길이     = 첫 onset → 마지막 onset (모든 리듬에서 같게 만든다)
  판독 시점   = 마지막 onset + delay. '끝'은 tapper 펌웨어가 알려 주는 마지막 onset 시각(외부 트리거)이다.
               트리거 없이 소자 신호로 끝을 찾으려면 그동안 계속 읽어야 하므로 그 비용도 같이 센다.
"""
import numpy as np

RHYTHMS = {  # onset 간격 비율 (합 = 1): 4번 누름 → 간격 3개
    "R1 균일": [1 / 3, 1 / 3, 1 / 3],
    "R2 앞에 몰림": [1 / 9, 1 / 9, 7 / 9],
    "R3 뒤에 몰림": [7 / 9, 1 / 9, 1 / 9],
    "R4 가운데 쉼": [1 / 9, 7 / 9, 1 / 9],
}


def make_schedule(n_per_class=60, span_s=1.8, jitter=0.10, min_gap_s=0.15, seed=0):
    """→ (onset 간격 목록[s] 배열 (시행, 3), 라벨). 흔들림을 넣은 뒤 합을 span_s로 다시 맞춘다."""
    rng = np.random.default_rng(seed)
    gaps, y = [], []
    for c, frac in enumerate(RHYTHMS.values()):
        for _ in range(n_per_class):
            g = np.array(frac) * span_s * (1 + jitter * rng.uniform(-1, 1, 3))
            g = g * span_s / g.sum()
            if g.min() < min_gap_s:
                g = np.maximum(g, min_gap_s)
                g = g * span_s / g.sum()
            gaps.append(g)
            y.append(c)
    idx = rng.permutation(len(y))
    return np.array(gaps)[idx], np.array(y)[idx]


def end_features(t, I, t_last_onset, delays=(0.3, 0.6, 1.0)):
    """마지막 onset 뒤 delay 시점의 전류(선형 보간). 기록이 그 시점까지 없으면 오류."""
    targets = t_last_onset + np.asarray(delays)
    if targets.max() > t[-1]:
        raise ValueError("판독 시점까지 기록이 없습니다")
    return np.interp(targets, t, I)


def full_features(t, I, t_first_onset, span_s, rate_hz=50):
    """'계속 읽기' 기준: 첫 onset부터 span+1초까지 일정 간격으로 다시 샘플링"""
    grid = t_first_onset + np.arange(0, span_s + 1.0, 1 / rate_hz)
    return np.interp(grid, t, I)


def cue_report(force_peaks, y):
    """리듬마다 누름 힘이 다르면 소자가 아니라 힘으로 구별했을 수 있다 → 클래스별 평균·표준편차"""
    return {int(c): (float(np.mean(force_peaks[y == c])), float(np.std(force_peaks[y == c]))) for c in np.unique(y)}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="리듬 일정 파일 만들기 → c_run.py / c_mock.py 입력")
    ap.add_argument("out", help="예: rhythm.npz")
    ap.add_argument("--n", type=int, default=60, help="리듬당 시행 수")
    ap.add_argument("--span", type=float, default=1.8, help="첫 누름 시작 → 마지막 누름 시작 [s]")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    gaps, y = make_schedule(a.n, a.span, seed=a.seed)
    np.savez(a.out, gaps=gaps, y=y, names=np.array(list(RHYTHMS)), span_s=a.span)
    print(f"저장: {a.out} — 시행 {len(y)}개 (리듬 {len(RHYTHMS)}종 × {a.n}), 간격 범위 {gaps.min():.2f}–{gaps.max():.2f} s")


if __name__ == "__main__":
    main()
