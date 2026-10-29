// C_tapper — 서보로 정해진 리듬을 누르고, 누르는 동안을 포함한 전체 힘–시간을 기록한다.
// 명령 (115200, 한 줄):
//   TARE                    빈 상태 영점
//   CAL,<g>                 <g>그램 추를 올린 상태에서 → 보정 계수 출력 (코드의 CAL_N_PER_COUNT에 넣기)
//   ANGLE,<도>              서보를 그 각도로 (힘–각도 표 만들 때)
//   T,<id>,g1,g2,g3         onset 간격(ms) 3개 → 4번 누름. 응답:
//      O,<id>,o1,o2,o3,o4   실제 onset 시각(ms, 명령 수신 기준)
//      FT,<id>,...  FV,<id>,...   힘 기록 시각(ms)과 값(N)
//      X,<id>,<마지막 onset ms>   '끝' 트리거: 판독 시점의 기준
// 서보 각도는 힘이 아니다. 실제 힘은 FV 기록으로 확인하고, 리듬마다 힘이 다른지 꼭 비교할 것.
// HX711 모듈은 기본 10 SPS인 것이 많다 (RATE 핀으로 80 SPS). 10 SPS면 80 ms 누름의 최대 힘을 놓칠 수 있다.
// 라이브러리: ESP32Servo, HX711 (bogde). 상태: 컴파일·실물 동작 미검증
#include <ESP32Servo.h>
#include <HX711.h>

const int PIN_SERVO = 18, PIN_DT = 16, PIN_SCK = 17;
int UP = 60, DOWN = 42;                 // ← 힘–각도 표로 정한 각도
const uint32_t HOLD_MS = 80, LEAD_MS = 500, POST_MS = 1500, MIN_GAP_MS = 150;
float CAL_N_PER_COUNT = 1.0e-5f;        // ← CAL 결과
long offset = 0;
Servo sv;
HX711 scale;
const int NMAX = 600;
uint32_t ft[NMAX];
float fv[NMAX];

void setup() {
  Serial.begin(115200);
  sv.attach(PIN_SERVO, 500, 2400);
  sv.write(UP);
  scale.begin(PIN_DT, PIN_SCK);
  delay(500);
  Serial.println("READY");
}

long avgRaw(int n) { long s = 0; for (int i = 0; i < n; i++) s += scale.read(); return s / n; }

void runRhythm(long id, const uint32_t *gaps) {
  uint32_t on[4], t0 = millis();
  on[0] = LEAD_MS;
  for (int k = 1; k < 4; k++) on[k] = on[k - 1] + gaps[k - 1];
  uint32_t endAt = on[3] + HOLD_MS + POST_MS;
  int k = 0, nf = 0;
  bool down = false;
  uint32_t onActual[4];
  while (true) {
    uint32_t t = millis() - t0;
    if (t >= endAt) break;
    if (!down && k < 4 && t >= on[k]) { sv.write(DOWN); down = true; onActual[k] = t; }
    if (down && t >= on[k] + HOLD_MS) { sv.write(UP); down = false; k++; }
    if (scale.is_ready() && nf < NMAX) { ft[nf] = t; fv[nf] = (scale.read() - offset) * CAL_N_PER_COUNT; nf++; }
  }
  sv.write(UP);
  Serial.printf("O,%ld,%lu,%lu,%lu,%lu\n", id, (unsigned long)onActual[0], (unsigned long)onActual[1],
                (unsigned long)onActual[2], (unsigned long)onActual[3]);
  Serial.printf("FT,%ld", id);
  for (int i = 0; i < nf; i++) Serial.printf(",%lu", (unsigned long)ft[i]);
  Serial.printf("\nFV,%ld", id);
  for (int i = 0; i < nf; i++) Serial.printf(",%.4f", fv[i]);
  Serial.printf("\nX,%ld,%lu\n", id, (unsigned long)onActual[3]);
}

void loop() {
  if (!Serial.available()) return;
  String s = Serial.readStringUntil('\n');
  s.trim();
  if (s == "TARE") { offset = avgRaw(20); Serial.printf("TARE,%ld\n", offset); return; }
  if (s.startsWith("CAL,")) {
    float g = s.substring(4).toFloat();
    long d = avgRaw(20) - offset;
    if (g <= 0 || d == 0) { Serial.println("E,cal"); return; }
    Serial.printf("CAL_N_PER_COUNT = %.8ef;\n", g * 9.81e-3f / d);
    return;
  }
  if (s.startsWith("ANGLE,")) { int a = s.substring(6).toInt(); if (a >= 0 && a <= 180) sv.write(a); return; }
  if (s.startsWith("T,")) {
    long v[4];
    int n = 0, p = 2;
    while (n < 4 && p <= (int)s.length()) {
      int q = s.indexOf(',', p);
      if (q < 0) q = s.length();
      String tok = s.substring(p, q);
      char *end;
      v[n++] = strtol(tok.c_str(), &end, 10);
      if (tok.length() == 0 || *end) { Serial.println("E,parse"); return; }
      p = q + 1;
    }
    if (n != 4 || p <= (int)s.length()) { Serial.println("E,count"); return; }
    uint32_t gaps[3];
    for (int i = 0; i < 3; i++) {
      if (v[i + 1] < (long)MIN_GAP_MS || v[i + 1] > 5000) { Serial.println("E,gap_range"); return; }
      gaps[i] = v[i + 1];
    }
    runRhythm(v[0], gaps);
  }
}
