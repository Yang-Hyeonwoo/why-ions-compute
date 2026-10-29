// B6_standalone — PC 없이: 저장된 입력을 재생해 소자에 걸고, 학습된 가중치로 판단하고, 알린다.
//   1단계(자동): ref_vectors.h의 저장 특징으로 점수를 계산해 Python 점수와 같은지 확인 (소자 사용 안 함)
//   2단계: inputs_test.h의 입력을 하나씩 재생 → 측정 → 판단 → LED·부저·OLED·블루투스
// 이것은 '저장 입력 재생형' 시제품이다. 연속 ECG를 실시간으로 처리하는 장치가 아니다.
// 화면 문구는 진단처럼 보이지 않게 '클래스 번호'로만 표시한다.
// 필요 파일: device_io.h, config.h, weights.h, ref_vectors.h, inputs_test.h (모두 export_mcu.py가 만듦)
// 라이브러리: + Adafruit SSD1306, Adafruit GFX. BLE는 ESP32 코어 내장(BLEDevice).
// 상태: 컴파일·실물 동작 미검증
#include "config.h"
#include "weights.h"
#include "ref_vectors.h"
#include "inputs_test.h"
#include "device_io.h"
#include <Adafruit_SSD1306.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>

const int NF_ALL = L * M;
const int LED_A = 26, LED_B = 33, BUZ = 27;   // 클래스 1 이상 = LED_A, 클래스 0 = LED_B
Adafruit_SSD1306 oled(128, 64, &Wire);
BLECharacteristic *chr = nullptr;
float st[NF_ALL];
PulseLog plog[NF_ALL];

// 점수 계산: MCU와 export_mcu.mcu_score()가 같은 순서로 계산한다
void scores(const float *state, bool alreadySelected, float *z) {
  for (int c = 0; c < NC; c++) {
    float s = BIAS[c];
    for (int i = 0; i < NF; i++) {
      float x = alreadySelected ? state[i] : state[FCOL[i]];
      s += W[c][i] * (x - MU[i]) / SD[i];
    }
    z[c] = s;
  }
}
int decide(const float *z) {
  if (NC == 1) return CLASS_ID[z[0] > 0 ? 1 : 0];
  int b = 0;
  for (int c = 1; c < NC; c++) if (z[c] > z[b]) b = c;
  return CLASS_ID[b];
}

void show(const char *a, const char *b) {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(2); oled.setCursor(0, 0); oled.println(a);
  oled.setTextSize(1); oled.setCursor(0, 40); oled.println(b);
  oled.display();
}

void bleBegin() {
  BLEDevice::init("IonRC-demo");
  BLEServer *srv = BLEDevice::createServer();
  BLEService *svc = srv->createService("6E400001-B5A3-F393-E0A9-E50E24DCCA9E");
  chr = svc->createCharacteristic("6E400003-B5A3-F393-E0A9-E50E24DCCA9E", BLECharacteristic::PROPERTY_NOTIFY);
  chr->addDescriptor(new BLE2902());
  svc->start();
  BLEDevice::getAdvertising()->addServiceUUID(svc->getUUID());
  BLEDevice::startAdvertising();
}

bool selfCheck() {   // 같은 특징 → 같은 점수인지 (허용 오차: 상대 1e-3)
  float z[NC];
  bool good = true;
  for (int r = 0; r < NREF; r++) {
    scores(XREF[r], true, z);
    for (int c = 0; c < NC; c++) {
      float d = fabsf(z[c] - SREF[r][c]), tol = 1e-3f * (1 + fabsf(SREF[r][c]));
      Serial.printf("R,%d,%d,%.6f,%.6f%s\n", r, c, z[c], SREF[r][c], d > tol ? ",FAIL" : "");
      if (d > tol) good = false;
    }
  }
  return good;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(LED_A, OUTPUT); pinMode(LED_B, OUTPUT); pinMode(BUZ, OUTPUT);
  bool io = ioBegin();
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (!selfCheck()) { show("CHECK", "score mismatch"); Serial.println("E,-1,score_mismatch"); ioReady = false; return; }
  if (!io) { show("IO ERR", "I2C/Vref"); Serial.println("E,-1,io_init"); return; }
  bleBegin();
  show("READY", RUN_NOTE);
  Serial.println("n,true_class,pred_class,ms,score0");
}

int n = 0, correct = 0;
void loop() {
  if (!ioReady || n >= NT) { setDeviceV(0.0f, V_LIMIT); delay(1000); return; }
  int nsat = 0;
  uint32_t t0 = millis();
  const char *err;
  if (!runSequence<L, M>(UT[n], MASK, V0, VA, THETA_US, REST_MS, V_LIMIT, plog, &nsat, &err)) {
    show("STOP", err); Serial.printf("E,%d,%s\n", n, err); ioReady = false; return;
  }
  for (int k = 0; k < NF_ALL; k++) st[k] = plog[k].iNa;
  float z[NC];
  scores(st, false, z);
  int pred = decide(z);
  uint32_t ms = millis() - t0;       // 휴지 시간 포함
  correct += (pred == YT[n]);
  digitalWrite(LED_A, pred != 0);
  digitalWrite(LED_B, pred == 0);
  if (pred != 0) { digitalWrite(BUZ, HIGH); delay(150); digitalWrite(BUZ, LOW); }
  char a[24], b[64];
  snprintf(a, sizeof a, "Class %d", pred);
  snprintf(b, sizeof b, "#%d agree %.2f %lums%s", n + 1, correct / float(n + 1), (unsigned long)ms, nsat ? " SAT" : "");
  show(a, b);
  if (pred != 0 && chr) { chr->setValue((uint8_t *)b, strlen(b)); chr->notify(); }
  Serial.printf("%d,%d,%d,%lu,%.5f\n", n, YT[n], pred, (unsigned long)ms, z[0]);
  n++;
}
