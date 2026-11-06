# ============================================================
# 준비 · package 설치 (한 번만)
#
# 전체 과정:
#
#   지금 VS Code가 쓰는 Python이 어느 것인지 찍기
#         ↓
#   바로 그 Python에 package 설치 (python/requirements.txt 목록)
#         ↓
#   설치한 package를 하나씩 불러 보기 → 모두 ok면 준비 끝
#
# 왜 이 파일로 설치하나:
#   컴퓨터에 Python이 두 개 이상 있으면, TERMINAL에서 설치한 Python과
#   ▷가 실행하는 Python이 서로 다를 수 있습니다. 그러면 설치했는데도
#   "No module named numpy" 오류가 납니다. 이 파일은 ▷가 실행하는 바로
#   그 Python(sys.executable)에 설치하므로 둘이 어긋나지 않습니다.
# ============================================================

import subprocess                   # 다른 프로그램(pip)을 실행하는 도구
import sys                          # 지금 실행 중인 Python의 정보
from pathlib import Path            # 폴더·파일 경로


# ============================================================
# 1. 지금 쓰는 Python 확인
# ============================================================

print("python  :", sys.executable)                        # ▷가 쓰는 Python 파일 위치
print("version :", sys.version.split()[0])                # 3.11 이상이면 됨

if sys.version_info < (3, 11):
    sys.exit("Python 3.11 이상이 필요합니다. 오른쪽 아래 상태 표시줄에서 다른 Python을 고르세요.")


# ============================================================
# 2. 설치할 목록 찾기
# ============================================================
#
# 이 파일은 ion-projects-code\mylabs 안에 있어야 합니다.
# 한 단계 위 폴더(ion-projects-code) 안의 python\requirements.txt를 찾습니다.

CODE = Path(__file__).resolve().parent.parent
REQ = CODE / "python" / "requirements.txt"
print("list    :", REQ)

if not REQ.exists():
    sys.exit("requirements.txt가 없습니다. VS Code가 연 폴더 바로 아래에 python 폴더가 보이는지 확인하세요.\n"
             "압축이 두 겹으로 풀렸다면 File → Open Folder로 안쪽 ion-projects-code를 여세요.")


# ============================================================
# 3. 바로 이 Python에 설치 (1–3분, 글자가 많이 흐릅니다)
# ============================================================

print("\ninstalling … (1-3 min)\n")
r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(REQ)])
if r.returncode != 0:
    sys.exit("\n설치 실패: 위의 빨간 ERROR 줄을 복사해 질문하세요.")


# ============================================================
# 4. 하나씩 불러 보기
# ============================================================

print("\ncheck:")
ok = True
for name in ["numpy", "scipy", "sklearn", "joblib", "matplotlib", "pyvisa", "serial", "wfdb"]:
    try:
        __import__(name)
        print(f"  {name:<11} ok")
    except Exception as e:                      # 하나라도 못 불러오면 이름과 이유를 찍는다
        ok = False
        print(f"  {name:<11} FAILED ({type(e).__name__})")

print("\nready. 다음은 p0_hello.py" if ok else "\nFAILED 줄이 있습니다. 그 줄을 복사해 질문하세요.")
