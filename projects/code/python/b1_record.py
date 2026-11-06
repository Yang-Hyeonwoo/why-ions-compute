"""B1a. 보드(B1a_rhythm.ino)가 보내는 버튼·조도 값을 CSV 한 파일에 이어 붙이고 파형 한 장을 그린다.

사용 (보드를 꽂고, 시리얼 모니터는 닫은 채로):
    python b1_record.py --port COM5 --label X --session s1 --seconds 40
    python b1_record.py --port COM5 --label Y --session s1 --seconds 40
기록 중에는 보드 버튼1로 리듬을 칩니다. 버튼2를 누르면 LED2가 따라 칠 리듬(X, Y 번갈아)을 보여 줍니다.
한 번 실행 = 한 라벨 묶음. 리듬과 리듬 사이는 2초 이상 쉽니다(분석이 2초 쉼으로 시행을 나눔).

CSV 열: session, label, n, time_s, button, light_V, source(measured = 실측, synthetic = 합성)
  n은 보드의 샘플 번호. 건너뛴 번호 = 빠진 샘플(누락).
  light_V = a0 / 4095 × 3.6 V (nRF52 기본 기준 전압 0.6 V × 1/6 이득을 가정. 조도 모듈을 연결했을 때만 의미 있음)
파형 그림: data/b1_<session>_<label>.png
"""
import argparse
import csv
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
COLS = ["session", "label", "n", "time_s", "button", "light_V", "source"]
V_FULL = 3.6   # 가정. 기준 전압 설정을 바꾸면 여기도 바꾼다


def parse(line):
    """'n,t_ms,btn,a0' 한 줄 → (n, t_s, btn, volts). 머리줄(#)이나 깨진 줄은 None."""
    if not line or line.startswith("#"):
        return None
    p = line.split(",")
    if len(p) != 4:
        return None
    try:
        n, t, b, a = int(p[0]), int(p[1]), int(p[2]), int(p[3])
    except ValueError:
        return None
    return n, t / 1000.0, b, a / 4095.0 * V_FULL


def record(port, seconds):
    import serial   # pyserial
    rows = []
    with serial.Serial(port, 115200, timeout=1) as s:
        s.reset_input_buffer()
        t_end = time.time() + seconds
        while time.time() < t_end:
            line = s.readline().decode("ascii", "ignore").strip()
            if line.startswith("#"):
                print(line)
            r = parse(line)
            if r:
                rows.append(r)
    return rows


def append_csv(path, session, label, rows):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        t0 = rows[0][1] if rows else 0.0
        for n, t, b, v in rows:
            w.writerow([session, label, n, f"{t - t0:.3f}", b, f"{v:.3f}", "measured"])


def plot(rows, out_png, title):
    from common import korean_plot
    plt = korean_plot()
    t0 = rows[0][1]
    t = [r[1] - t0 for r in rows]
    fig, ax = plt.subplots(2, 1, figsize=(8, 4), sharex=True)
    ax[0].step(t, [r[2] for r in rows], where="post", color="#2b59c3")
    ax[0].set_ylabel("버튼")
    ax[1].plot(t, [r[3] for r in rows], color="#0e8a83", lw=0.8)
    ax[1].set_ylabel("조도 (V)")
    ax[1].set_xlabel("시간 (s)")
    ax[0].set_title(title)
    fig.tight_layout()
    fig.savefig(out_png, dpi=120)
    print("plot:", out_png)


def report(rows):
    """누락·접점 튐·포화를 숫자로 알려 준다."""
    gaps = sum(1 for a, b in zip(rows, rows[1:]) if b[0] - a[0] != 1)
    edges = [rows[i][1] for i in range(1, len(rows)) if rows[i][2] and not rows[i - 1][2]]
    falls = [rows[i][1] for i in range(1, len(rows)) if not rows[i][2] and rows[i - 1][2]]
    # b1_memory.py와 같은 기준: 뗀 뒤 30 ms 안에 다시 눌리면 접점 튐
    bounce = sum(1 for e in edges if any(0 <= e - f < 0.03 for f in falls))
    sat = sum(1 for r in rows if r[3] > V_FULL * 0.98 or r[3] < 0.02)
    print(f"samples {len(rows)}, presses {len(edges)}, dropped gaps {gaps}, bounces (re-press within 30 ms) {bounce}, light saturated samples {sat}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--label", required=True, help="X 또는 Y처럼 이번 묶음에서 친 리듬 이름")
    ap.add_argument("--session", required=True, help="날짜나 회차. 예: s1")
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--out", default=os.path.join(HERE, "data", "b1_taps.csv"))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    rows = record(a.port, a.seconds)
    if not rows:
        raise SystemExit("받은 줄이 없습니다. COM 포트, 시리얼 모니터가 닫혔는지, 펌웨어가 올라갔는지 확인하세요.")
    append_csv(a.out, a.session, a.label, rows)
    report(rows)
    plot(rows, os.path.join(os.path.dirname(a.out), f"b1_{a.session}_{a.label}.png"), f"{a.session} · {a.label}")
    print("CSV:", a.out)
