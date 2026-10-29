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
    for name in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"):
        if name in have:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False
    return plt
