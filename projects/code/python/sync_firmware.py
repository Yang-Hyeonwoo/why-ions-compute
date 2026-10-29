"""firmware/common/device_io.h를 각 스케치 폴더로 복사한다 (아두이노는 다른 폴더의 헤더를 바로 못 씀).
device_io.h를 고친 뒤 한 번 실행: python sync_firmware.py
"""
import os
import shutil

FW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware")
src = os.path.join(FW, "common", "device_io.h")
for sketch in ("B4_test", "B5_collect", "B6_standalone"):
    shutil.copy(src, os.path.join(FW, sketch, "device_io.h"))
    print("복사:", sketch)
