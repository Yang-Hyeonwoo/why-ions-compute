// B5_collect — PC(board_collect.py)가 보낸 입력으로 펄스열을 걸고, 상태·실제 펄스 길이를 돌려준다.
// 통신 약속은 board_collect.py 맨 위 설명과 같다. 입력이 조금이라도 이상하면 소자를 구동하지 않고 E 줄을 보낸다.
// 필요 파일: device_io.h, config.h (export_mcu.py가 만든 것, 또는 예시)
// 상태: 컴파일·실물 동작 미검증
#include "config.h"
#include "device_io.h"
#include <stdlib.h>

const int NF_ALL = L * M;
const size_t LINE_CAP = 16 + 12 * L;
char line[16 + 12 * L];
float u[L];
PulseLog plog[NF_ALL];

// 한 줄 읽기: 첫 글자부터 timeoutMs 안에 \n이 와야 하고, 길이를 넘으면 실패
bool readLine(uint32_t timeoutMs) {
  size_t n = 0;
  uint32_t t0 = millis();
  while (millis() - t0 < timeoutMs) {
    if (!Serial.available()) continue;
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') { line[n] = 0; return n > 0; }
    if (n >= LINE_CAP - 1) { while (Serial.available()) Serial.read(); return false; }
    line[n++] = c;
  }
  return false;
}

bool parseFloatStrict(const char *s, float *v) {
  char *end;
  *v = strtof(s, &end);
  return end != s && *end == 0 && isfinite(*v);
}

void reject(long id, const char *why) { Serial.printf("E,%ld,%s\n", id, why); }

void setup() {
  Serial.begin(115200);
  delay(500);
  if (!ioBegin()) { reject(-1, "io_init"); return; }
  Serial.printf("READY L=%d M=%d VREF=%.4f ADC_us=%lu %s\n", L, M, VREF, (unsigned long)adcReadUs, RUN_NOTE);
}

void loop() {
  if (!ioReady || !Serial.available()) return;
  if (!readLine(500)) { reject(-1, "line_timeout_or_too_long"); return; }
  char *save, *tok = strtok_r(line, ",", &save);
  if (!tok || strcmp(tok, "B") != 0) { reject(-1, "not_B"); return; }
  tok = strtok_r(NULL, ",", &save);
  char *end;
  long id = tok ? strtol(tok, &end, 10) : -1;
  if (!tok || *end || id < 0) { reject(-1, "bad_id"); return; }
  tok = strtok_r(NULL, ",", &save);
  long l = tok ? strtol(tok, &end, 10) : -1;
  if (!tok || *end || l != L) { reject(id, "L_mismatch"); return; }
  for (int i = 0; i < L; i++) {
    tok = strtok_r(NULL, ",", &save);
    if (!tok || !parseFloatStrict(tok, &u[i]) || u[i] < 0 || u[i] > 1) { reject(id, "bad_value"); return; }
  }
  if (strtok_r(NULL, ",", &save)) { reject(id, "too_many_values"); return; }
  int nsat = 0;
  const char *err;
  if (!runSequence<L, M>(u, MASK, V0, VA, THETA_US, REST_MS, V_LIMIT, plog, &nsat, &err)) {
    reject(id, err);
    if (strncmp(err, "dac_i2c", 7) == 0) ioReady = false;   // 통신 실패 뒤에는 더 구동하지 않음 (리셋 필요)
    return;
  }
  // 측정이 다 끝난 뒤에 한꺼번에 보낸다 (보내는 시간이 펄스 타이밍에 섞이지 않게)
  // S 전류[nA] · V 펄스 끝 소자 전압[V] · P 명령 유지 시간[µs] · R 읽기 끝 시각[µs] · Q 포화 수
  Serial.printf("S,%ld", id);
  for (int k = 0; k < NF_ALL; k++) Serial.printf(",%.4f", plog[k].iNa);
  Serial.printf("\nV,%ld", id);
  for (int k = 0; k < NF_ALL; k++) Serial.printf(",%.5f", plog[k].vDev);
  Serial.printf("\nP,%ld", id);
  for (int k = 0; k < NF_ALL; k++) Serial.printf(",%lu", (unsigned long)plog[k].periodUs);
  Serial.printf("\nR,%ld", id);
  for (int k = 0; k < NF_ALL; k++) Serial.printf(",%lu", (unsigned long)plog[k].readEndUs);
  Serial.printf("\nQ,%ld,%d\n", id, nsat);
}
