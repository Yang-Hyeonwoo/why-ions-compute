// [모의 예시: 장비 없이 만든 값. 실제 측정 후 export_mcu.py로 다시 만들 것] 자동 생성: export_mcu.py — 손으로 고치지 말 것
#pragma once
const int L = 12;
const int M = 4;
const float MASK[M] = {0.84f,0.43f,0.97f,0.61f};
const float V0 = 0.0f;
const float VA = 0.8f;
const uint32_t THETA_US = 50000;
const uint32_t REST_MS = 2000;
const float V_LIMIT = 1.0f;
const char RUN_NOTE[] = "2026-10-29 19:21:16 dev01";
