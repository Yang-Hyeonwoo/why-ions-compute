"""공통 도구: 실행 설정(manifest), 원자적 저장, 조건 비교.

모든 측정은 runs/<이름>/ 폴더 하나에 모인다.
  manifest.json   이 측정의 조건(장비·소자·인코딩·입력 파일 지문). 재개할 때 이것과 다르면 거부.
  checkpoint.npz  지금까지의 상태 행렬과 '끝난 시행' 표시. 시행 하나가 끝날 때마다 통째로 교체.
  raw/trial_00012.npz  시행 하나의 원시 기록(호스트 시각, 설정 전압, 측정 전압, 전류, 상태).
"""
import hashlib
import json
import os
import platform
import time

import numpy as np

# 재개할 때 반드시 같아야 하는 설정 묶음
MATCH_KEYS = ("instrument", "device", "encoding")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)          # 같은 디스크 안에서는 한 번에 바뀜 → 반쯤 쓴 파일이 남지 않음


def atomic_save_npz(path, **arrays):
    tmp = path + ".tmp.npz"        # np.savez는 .npz를 붙이므로 이름을 맞춰 둔다
    np.savez(tmp, **arrays)
    os.replace(tmp, path)


def array_sha(a):
    a = np.ascontiguousarray(a)
    return hashlib.sha256(a.tobytes() + str(a.shape).encode() + str(a.dtype).encode()).hexdigest()[:16]


def make_manifest(cfg, input_sha, n_trials, n_features):
    m = {k: cfg[k] for k in MATCH_KEYS}
    m.update(input_sha=input_sha, n_trials=int(n_trials), n_features=int(n_features),
             created=time.strftime("%Y-%m-%d %H:%M:%S"), python=platform.python_version(),
             numpy=np.__version__, note=cfg.get("note", ""))
    return m


def manifest_mismatch(old, new):
    """재개해도 되는지: 다르면 다른 항목 이름 목록, 같으면 빈 목록."""
    bad = [k for k in MATCH_KEYS + ("input_sha", "n_trials", "n_features") if old.get(k) != new.get(k)]
    return bad


def korean_plot():
    """matplotlib을 그림 파일 모드로 켜고 한글 글꼴을 고른다 (Windows: 맑은 고딕)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("Pretendard", "Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"):
        if name in have:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False
    # 2026-11-06 학습 피드백: 글씨가 작고 흐려 깨져 보였다 → 글자를 키우고 해상도를 올린다 (모든 그림 공통)
    plt.rcParams.update({
        "font.size": 11, "axes.titlesize": 11.5, "axes.labelsize": 11,
        "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 9.5,
        "figure.dpi": 100, "savefig.dpi": 200, "savefig.bbox": "tight", "savefig.pad_inches": 0.12,
        "legend.frameon": False, "mathtext.default": "regular",  # 2026-11-06: 범례 테두리 없앰, V_set → 아래첨자
        "axes.titleweight": "semibold", "axes.titlelocation": "left", "axes.titlepad": 8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#5a6270", "axes.labelcolor": "#2b313a", "xtick.color": "#5a6270", "ytick.color": "#5a6270",
    })
    return plt


def print_table(headers, rows, left=()):
    """명령 창용 표. 값이 열 제목 바로 아래 가운데에 오게 찍는다(같은 열의 값끼리는 오른쪽 끝을 맞춤).
    2026-11-06 학습 피드백: 한글이 섞이면 명령 창에서 칸이 어긋나므로 제목·값은 영어·숫자만 쓴다.
    headers: 열 제목 목록. 'sampling rate|(Hz)'처럼 |로 나누면 제목을 두 줄로 쓴다(표 폭을 줄이려고).
    rows: 각 줄의 값 목록, left: 글자 열처럼 왼쪽 정렬할 열 번호."""
    head = [str(h).split("|") for h in headers]
    nh = max(len(h) for h in head)
    head = [[""] * (nh - len(h)) + h for h in head]          # 한 줄 제목은 아래 줄에 맞춤
    body = [[str(v) for v in r] for r in rows]
    n = len(head)
    vw = [max([len(r[i]) for r in body] or [0]) for i in range(n)]   # 값 폭
    w = [max(max(len(x) for x in head[i]), vw[i]) for i in range(n)]  # 열 폭

    def cell(i, text, is_head):
        if i in left:
            return text.ljust(w[i])
        if is_head:
            return text.center(w[i])
        block = text.rjust(vw[i])                 # 값끼리 오른쪽 끝(소수점) 맞춤
        pad = (w[i] - vw[i]) // 2                 # 그 덩어리를 제목 아래 가운데로
        return (" " * pad + block).ljust(w[i])

    for k in range(nh):
        print("  ".join(cell(i, head[i][k], True) for i in range(n)).rstrip())
    print("  ".join("-" * w[i] for i in range(n)))
    for r in body:
        print("  ".join(cell(i, r[i], False) for i in range(n)).rstrip())
