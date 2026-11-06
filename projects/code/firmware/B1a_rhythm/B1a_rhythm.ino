// B1a. 버튼 리듬 기록 (NU40 DK, 추가 부품 없이)
// - 보드 버튼1(pin 11)을 200 Hz로 읽어 PC로 보낸다. 누르면 LED1이 켜진다.
// - 버튼2(pin 12)를 누르면 LED2가 따라 칠 리듬(X, Y 번갈아)을 한 번 보여 준다.
// - A0(P0.02)에 37종 키트의 조도 모듈 S핀을 연결하면 a0 열에 빛 세기가 같이 기록된다(선택).
//   연결하지 않으면 a0 값은 떠 있는 핀의 잡음이니 무시한다.
// 출력 한 줄: n,t_ms,btn,a0   (n = 샘플 번호. 중간에 빠진 줄이 있으면 PC 쪽에서 n이 건너뛴다)
// 2026-11-03 NU40용 컴파일 확인. 업로드·실물 동작은 미확인.
#if !defined(ARDUINO_ARCH_ESP32)
#include <Adafruit_TinyUSB.h>   // NU40: USB 시리얼(Serial)을 쓰려면 필요
#endif

const int BTN = PIN_BUTTON1, BTN_GUIDE = PIN_BUTTON2;
const int LED_TAP = PIN_LED1, LED_GUIDE = PIN_LED2;
const uint32_t PERIOD_US = 5000;   // 200 Hz

// 따라 칠 리듬: 누름 시작 시각(ms). 둘 다 5번, 처음→마지막 2000 ms, 마지막 간격 500 ms. 앞쪽 순서만 다르다
const uint16_t PAT_X[5] = {0, 250, 500, 1500, 2000};
const uint16_t PAT_Y[5] = {0, 1000, 1250, 1500, 2000};

int idleLevel;      // 켤 때 버튼을 안 누른 상태의 값 (보드마다 눌림이 HIGH인지 LOW인지 몰라도 되게)
uint32_t n = 0, next_us;
bool nextIsX = true;

void playGuide(const uint16_t* p) {
  uint32_t t0 = millis();
  for (int i = 0; i < 5; i++) {
    while (millis() - t0 < p[i]) {}
    digitalWrite(LED_GUIDE, HIGH);
    delay(80);
    digitalWrite(LED_GUIDE, LOW);
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) delay(10);
  pinMode(BTN, INPUT_PULLUP);
  pinMode(BTN_GUIDE, INPUT_PULLUP);
  pinMode(LED_TAP, OUTPUT);
  pinMode(LED_GUIDE, OUTPUT);
  analogReadResolution(12);           // 0–4095
  delay(50);
  idleLevel = digitalRead(BTN);
  Serial.println("# B1a rhythm logger. columns: n,t_ms,btn,a0");
  Serial.print("# idle level = ");
  Serial.println(idleLevel);
  next_us = micros();
}

void loop() {
  if (digitalRead(BTN_GUIDE) != idleLevel) {
    Serial.println(nextIsX ? "# guide X" : "# guide Y");
    playGuide(nextIsX ? PAT_X : PAT_Y);
    nextIsX = !nextIsX;
    while (digitalRead(BTN_GUIDE) != idleLevel) {}
    next_us = micros();
  }
  if ((int32_t)(micros() - next_us) < 0) return;
  next_us += PERIOD_US;
  int pressed = digitalRead(BTN) != idleLevel;
  digitalWrite(LED_TAP, pressed);
  int a0 = analogRead(A0);
  Serial.print(n++);
  Serial.print(',');
  Serial.print(millis());
  Serial.print(',');
  Serial.print(pressed);
  Serial.print(',');
  Serial.println(a0);
}
