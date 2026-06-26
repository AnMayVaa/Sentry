# Sentry — รายงานพัฒนาการด้านเทคนิคเชิงลึก
**โปรเจกต์:** ระบบตรวจจับการล้มอัจฉริยะโดยใช้คลื่น Wi-Fi CSI สำหรับผู้สูงอายุในที่อยู่อาศัย
**งานแข่งขัน:** NSC 2026 (การแข่งขันซอฟต์แวร์แห่งชาติ ครั้งที่ 28) และ The I-New Gen Award 2026 (Thailand New Gen Inventors Award)
**จัดทำเพื่อ:** ทีมนักวิจัยและวิศวกรร่วม
**วันที่:** มิถุนายน 2569

---

## ภาพรวมโปรเจกต์

**Sentry** คือระบบตรวจจับการล้มแบบ Non-invasive (ไม่ต้องสวมใส่อุปกรณ์, ไม่ใช้กล้อง) โดยใช้คลื่นวิทยุ Wi-Fi ที่มองไม่เห็นในการตรวจจับการเคลื่อนไหวของมนุษย์แบบ Real-time

หลักการทำงาน: เมื่อร่างกายมนุษย์เคลื่อนที่ผ่านคลื่น Wi-Fi ที่กระจายอยู่ในห้อง ร่างกายจะ **สะท้อน (Reflect)**, **หักเห (Diffract)**, และ **ดูดซับ (Absorb)** คลื่นเหล่านั้น ทำให้ค่าสัญญาณที่ตัวรับได้รับเปลี่ยนแปลงในรูปแบบเฉพาะ ระบบ Sentry อ่านการเปลี่ยนแปลงนี้และส่งให้ AI ตัดสินใจว่าเกิดอะไรขึ้น

### Stack ภาพรวม

| ชั้น | เทคโนโลยี |
|---|---|
| ฮาร์ดแวร์ | ESP32 (Tx + Rx Node) |
| Firmware | Arduino IDE (ESP-IDF Native Wrapper) |
| Edge Server | Raspberry Pi 5 (8GB RAM) |
| Backend | Python — `asyncio`, `websockets`, `scikit-learn`, `numpy` |
| Frontend | HTML/CSS/JS — `Chart.js` |
| เครือข่าย | Cloudflare Tunnel → `csi.ohmpatumwan.com` |
| การแจ้งเตือน | LINE Messaging API (Flex Message) |

---

## Phase 1 — การติดตั้งฮาร์ดแวร์ & การดึงข้อมูล CSI ดิบ

### เป้าหมาย
สร้างช่องทางรับส่งข้อมูล Wi-Fi CSI ระหว่าง ESP32 สองตัว และดึงค่า Subcarrier Amplitude ออกมาได้ที่ความเร็ว 30 เฟรม/วินาที

### ทฤษฎีเชิงลึก: CSI คืออะไร?

Wi-Fi มาตรฐาน 802.11 ใช้เทคนิค **OFDM (Orthogonal Frequency Division Multiplexing)** ซึ่งแบ่งสัญญาณออกเป็น **52 ช่องความถี่ย่อย (Subcarrier)** ที่ทำงานพร้อมกัน

**Channel State Information (CSI)** คือตัวเลขที่บอกว่า "แต่ละ Subcarrier ถูกส่งผ่านอากาศไปแล้ว ถูกรับมาด้วยความแรงและเฟสเท่าใด" ซึ่งแสดงในรูป Complex Number `H = A * e^(jθ)` โดย:
- `A` = Amplitude (ความแรงสัญญาณ)
- `θ` = Phase (เฟสสัญญาณ)

เราใช้เฉพาะ **A (Amplitude)** ของทั้ง 52 Subcarrier เนื่องจาก Phase มีความผันผวนสูงจาก Clock Offset ระหว่างอุปกรณ์

**หลักการ Multipath Propagation:**
คลื่น Wi-Fi จากตัวส่งไปถึงตัวรับผ่านหลายเส้นทางพร้อมกัน (สะท้อนผนัง, พื้น, เพดาน, วัตถุ) เมื่อมีร่างกายมนุษย์เคลื่อนที่เข้ามา เส้นทางเหล่านี้เปลี่ยนแปลง ส่งผลให้ Amplitude ของ Subcarrier แต่ละตัวเปลี่ยนไปในรูปแบบที่วัดได้ ซึ่งเป็น "ลายนิ้วมือ" ของการเคลื่อนไหว

### วิธีการ

**ฝั่ง Transmitter (Tx) ESP32:**
- ใช้ ESP-NOW Protocol ส่งแพ็คเก็ต `802.11 QoS Data` ด้วยความเร็ว **30 ครั้ง/วินาที**
- เหตุที่ต้องใช้ ESP-NOW: บังคับให้ฮาร์ดแวร์ใช้ OFDM Rate 54 Mbps ซึ่งมี Subcarrier ครบ 52 ตัว (หากใช้ Rate ต่ำกว่า จะใช้ CCK Modulation ซึ่งไม่มี CSI Data)
- แพ็คเก็ตไม่จำเป็นต้องมีข้อมูลจริง — ใช้เพื่อ "บังคับสร้างคลื่น OFDM" เท่านั้น

**ฝั่ง Receiver (Rx) ESP32:**
- เปิดโหมด **Promiscuous Mode** ผ่าน `esp_wifi_set_promiscuous(true)` เพื่อรับ **ทุกแพ็คเก็ต** ในอากาศโดยไม่ต้องจับคู่ก่อน
- ลงทะเบียน Callback Function ผ่าน `esp_wifi_set_csi_rx_cb()` ซึ่ง ESP-IDF จะเรียกใช้ทุกครั้งที่รับแพ็คเก็ตใหม่พร้อมข้อมูล CSI
- กรองเฉพาะแพ็คเก็ตจาก MAC Address ของ Tx Node
- ดึง Array `int8_t[52]` ออกจาก struct `wifi_csi_info_t.buf` และส่งต่อผ่าน USB Serial

### ปัญหา & วิธีแก้

**ปัญหา:** Rx ESP32 ล่มและรีบูตซ้ำๆ พร้อมข้อความ:
```
E (xxxx) task_wdt: Task watchdog got triggered. Tasks that did not reset the watchdog in time: - IDLE (CPU 0)
```

**สาเหตุเชิงเทคนิค:** UART ที่ `115200` baud ส่งข้อมูลได้ **~14,400 bytes/วินาที**  
แต่ข้อมูล CSI ต้องการ: `52 floats × 8 chars × 30 Hz = ~12,480 bytes/วินาที`  
เมื่อรวมกับ Newline, RSSI, Header → เกิน Capacity พอดี ทำให้ UART TX Buffer เต็ม CPU วน Wait Loop, Watchdog ไม่ถูก Feed, ระบบล่ม

**วิธีแก้:** เพิ่ม Baud Rate เป็น `460800` (4× เร็วขึ้น) → Bandwidth ขยายเป็น ~57,600 bytes/วินาที ซึ่งมากกว่าที่ต้องการถึง 4.6 เท่า

```c
// sdkconfig
CONFIG_ESP_CONSOLE_UART_BAUDRATE=460800

// rx_main.c
uart_config_t uart_config = {
    .baud_rate = 460800,
    ...
};
```

---

## Phase 2 — ระบบ Machine Learning ตรวจจับการล้ม

### เป้าหมาย
ฝึก AI Model ให้จำแนกสถานะจากสตรีม CSI เป็น 3 คลาส: หยุดนิ่ง (0), เคลื่อนไหว (1), ล้ม (2)

### กระบวนการ Feature Engineering เชิงลึก

**Sliding Window:**
เก็บ Frame ล่าสุด 45 เฟรม (= 1.5 วินาที ที่ 30Hz) ไว้ใน `deque(maxlen=45)` เมื่อ Window เต็ม จะดึง Feature ดังนี้:

| Feature | สูตรคณิตศาสตร์ | ความหมายทางกายภาพ |
|---|---|---|
| **Variance** | `σ² = Σ(xᵢ - x̄)² / N` | ความผันผวนโดยรวมของคลื่น — สูง = มีการเคลื่อนไหว |
| **Std Dev** | `σ = √σ²` | ส่วนเบี่ยงเบนมาตรฐาน |
| **Mean** | `x̄ = Σxᵢ / N` | ค่าเฉลี่ยสัญญาณ |
| **Rate of Change** | `Δx = xₙ - xₙ₋₁` | ความเร็วของการเปลี่ยนแปลง — สูงสุดช่วง Impact |
| **Peak-to-Peak** | `max(x) - min(x)` | ช่วงสัญญาณ |

โดย Array มิติเดียว `xᵢ` ในที่นี้คือค่าเฉลี่ยของ 52 Subcarrier Amplitude ในแต่ละ Frame

**Python Implementation (Optimized):**
```python
def extract_features_np(history_array):
    # history_array shape: (45, 52) - 45 frames, 52 subcarriers each
    mean_per_frame = np.mean(history_array, axis=1)  # (45,)
    
    variance    = np.var(mean_per_frame)
    std_dev     = np.std(mean_per_frame)
    mean_val    = np.mean(mean_per_frame)
    roc         = np.mean(np.diff(mean_per_frame))   # avg rate of change
    peak2peak   = np.ptp(mean_per_frame)
    
    return [variance, std_dev, mean_val, roc, peak2peak]
```

**ทำไมถึงเลือก Random Forest:**
- ทนทานต่อ Noise สูง (คลื่น Wi-Fi มี Noise เยอะ)
- ทำงานได้ดีกับ Dataset ขนาดเล็ก (เราไม่มีข้อมูลหลายพันชั่วโมง)
- Inference Time < 1ms บน Raspberry Pi 5 ← สำคัญมากสำหรับ Real-time
- ไม่ Overfit ง่ายเหมือน Neural Network

### ปัญหา & วิธีแก้

**ปัญหา 1 — Physics Blind Spot (AI ตรวจไม่เจอการล้ม):**
AI จัดทุกอย่างเป็น "หยุดนิ่ง" แม้แต่ตอนล้มจริงๆ

**สาเหตุ:** บันทึกข้อมูล `falling.csv` โดยยืนอยู่ *หลัง* แนวเสาอากาศ คลื่น Wi-Fi ไม่ได้วิ่งผ่านร่างกายระหว่างการล้ม จึงไม่มีการเปลี่ยนแปลงของ Amplitude เลย  
**แก้ไข:** ย้ายตำแหน่งบันทึกให้ยืน**ระหว่าง**เสาอากาศ Tx กับ Rx โดยตรง — ค่า Variance พุ่งขึ้นถึง 40–80 ระหว่างการล้ม

---

**ปัญหา 2 — Label Contamination (AI จำแนกการเดินเป็นการล้ม):**

**สาเหตุ:** `falling.csv` ถูกบันทึกเป็น Session ยาว ประกอบด้วย:
- ช่วงเดินไปยังจุดล้ม (Variance ต่ำ-กลาง)
- ช่วงล้มจริง (Variance สูงมาก)
- ช่วงนอนนิ่งหลังล้ม (Variance ต่ำ)

ข้อมูลทั้งหมดถูก Label ว่า "Fall" แต่ 80% มีลักษณะทางคณิตศาสตร์คล้ายกับ "Walking" หรือ "Static"

**แก้ไข — Automated Data Cleaner:**
```python
# ใน train_model.py
def clean_fall_data(df):
    window_variances = []
    for i in range(0, len(df) - WINDOW_SIZE, STEP):
        window = df.iloc[i:i+WINDOW_SIZE]
        var = np.var(np.mean(window.values, axis=1))
        window_variances.append((i, var))
    
    # เก็บเฉพาะ Top 15% ที่มี Variance สูงสุด (= ช่วง Impact จริงๆ)
    threshold = np.percentile([v for _, v in window_variances], 85)
    return [i for i, v in window_variances if v >= threshold]
```

---

**ปัญหา 3 — UI กระพริบ / False Positive:**

**สาเหตุ:** การกระแทกโต๊ะ, จาม, หรือนั่งลงเร็วๆ สร้าง Variance Spike ชั่วขณะที่สูงพอจะ Trigger "FALL"

**แก้ไข — Temporal Sequence State Machine:**
การล้มจริงทางฟิสิกส์มีรูปแบบ **IMPACT → STILLNESS** ที่ชัดเจน:

```
State Machine Logic:
─────────────────────────────────────────────────
current_state = STATIC (0)

เมื่อ: variance >= threshold
  → current_state = MOVEMENT (1)
  
เมื่อ: ML Model ทำนาย "FALL" (2) AND variance >= threshold
  → potential_fall = True
  → potential_fall_time = now()
  
เมื่อ: potential_fall = True AND (now() - potential_fall_time) > 3 วินาที AND variance < threshold
  → current_state = CONFIRMED FALL (2) ← เงียบนิ่งหลัง Impact
  → ส่ง LINE Alert

เมื่อ: potential_fall = True AND ยังมีการเคลื่อนไหว
  → ยกเลิก potential_fall ← คนยังเคลื่อนไหวอยู่ แสดงว่าไม่ใช่การล้ม
─────────────────────────────────────────────────
```

---

## Phase 3 — ระบบแจ้งเตือนฉุกเฉิน (LINE API)

### เป้าหมาย
แจ้งเตือนผู้ดูแลแบบ Real-time ผ่าน LINE เมื่อ State Machine ยืนยันการล้ม

### วิธีการ
**LINE Flex Message** คือ JSON-based Rich Message ที่ออกแบบ Layout ได้เอง ใช้ `line_notifier.py` สร้าง Card สีแดงฉุกเฉินที่ประกอบด้วย:
- เวลาที่เกิดเหตุ
- ชื่อห้อง / ตำแหน่ง
- ปุ่ม "โทร 1669" ที่กดแล้วโทรออกทันที

```python
# โครงสร้าง API Call
headers = {
    "Authorization": f"Bearer {LINE_TOKEN}",
    "Content-Type": "application/json"
}
payload = {
    "to": GROUP_ID,
    "messages": [flex_message_object]  # JSON object ที่ออกแบบเอง
}
requests.post("https://api.line.me/v2/bot/message/push", 
              headers=headers, json=payload)
```

### ปัญหา & วิธีแก้

**ปัญหา — API Spam + Main Thread Blocking:**

หากคนนอนอยู่กับพื้น Python Loop 30Hz จะส่ง API ซ้ำหลายพันครั้ง/นาที + `requests.post()` เป็น Blocking Call ทำให้ Graph ค้าง

**แก้ไข 1 — Non-blocking Thread:**
```python
# ส่ง Alert ใน Background Thread ไม่บล็อก Main Loop
threading.Thread(
    target=send_fall_alert,
    args=(location_name,),
    daemon=True  # Thread ตายพร้อม Main Process อัตโนมัติ
).start()
```

**แก้ไข 2 — Cooldown Timer:**
```python
ALERT_COOLDOWN = 60  # วินาที

if current_time - node.last_line_alert_time > ALERT_COOLDOWN:
    # ส่ง Alert ได้
    node.last_line_alert_time = current_time
```

---

## Phase 4 (ต้น) — ปุ่ม SOS ฉุกเฉินทางฮาร์ดแวร์

### เป้าหมาย
ให้ผู้สูงอายุกด SOS ได้ตลอดเวลาโดยไม่ต้องรอ AI ยืนยัน

### วิธีการ — การตรวจจับด้วยฟิสิกส์แทนซอฟต์แวร์

ปัญหาหลัก: Rx ESP32 อยู่ใน **Promiscuous Mode** ซึ่ง MAC Layer ของ ESP32 จะบล็อก ESP-NOW Callback (`espnow_recv_cb`) ทำให้ SOS Message จาก Tx ถูกทิ้งไปก่อนถึง Application Layer

**วิธีแก้เชิงฟิสิกส์ — Packet Size Fingerprinting:**

```
ปกติ: Tx ส่งแพ็คเก็ต CSI ขนาด ~16 bytes
เมื่อกด SOS: Tx เพิ่ม Padding ทำให้แพ็คเก็ตโตขึ้นเป็น 150 bytes

ใน Promiscuous Callback ของ Rx:
  if (info->rx_ctrl.sig_len > 100) {
      // ไม่ต้องถอดรหัส Payload เลย
      // ขนาดแพ็คเก็ต = รหัส SOS
      send_sos_alert_to_python();
  }
```

ทั้ง Tx และ Rx BOOT Button ทำงานเป็น Panic Button โดยทั้งคู่ส่ง `SOS_ALERT` string ไปยัง Python ผ่าน Serial Port

### ปัญหา 2 — Python Crash จาก Unexpected String

```python
# Bug: Callback คาดหวัง (list, int) แต่ได้รับ string
def data_received(amplitudes, rssi, location_name):
    mean = np.mean(amplitudes)  # TypeError: cannot get mean of string "SOS"

# แก้ไขใน serial_reader.py:
if line.startswith("SOS_ALERT"):
    callback("SOS", 0, location)  # ส่ง dummy tuple แทน
    return
```

---

## Phase 1.5 — Wireless UDP Receiver (ไร้สาย)

### เป้าหมาย
ถอดสาย USB ออก ให้ ESP32 ส่งข้อมูล CSI ผ่าน Wi-Fi มายัง PC โดยตรง

### วิธีการ
เขียน Firmware ใหม่ใน Arduino IDE (`.ino`) เนื่องจาก ESP-IDF C Build Environment บน Windows มีปัญหา `PATH` และ Python alias ขัดแย้งกันทำให้ Flash ไม่ได้ การใช้ Arduino Core แก้ปัญหานี้ได้เพราะ Arduino Core ครอบ ESP-IDF ไว้ข้างใน สามารถเรียก `<esp_wifi.h>` และ Promiscuous Mode API ได้เหมือนเดิม แต่ Flash ด้วย GUI คลิกเดียว

การทำงานของ Firmware ใหม่:
- Rx Node ยังคง Sniff CSI ใน Promiscuous Mode เหมือนเดิม
- แทนที่จะพิมพ์ผ่าน Serial, เชื่อมต่อ Wi-Fi Router และส่ง UDP Packet ไปยัง PC บน Port 5000
- Python GUI ฝั่ง PC รับ UDP แทน Serial

### ปัญหา & วิธีแก้เชิงลึก

**ปัญหา 2 — Single Antenna, Two Frequencies (วิกฤตฟิสิกส์):**

ESP32 มีเสาอากาศเดียว แต่ต้องทำงาน 2 อย่างพร้อมกัน:
1. **ฟังสัญญาณ CSI** จาก Tx (Channel 6) ใน Promiscuous Mode
2. **ส่ง UDP** ไปยัง PC ผ่าน Home Router (Channel 11)

เสาอากาศ RF Tuner ตั้งได้ครั้งละ **1 Channel เท่านั้น** เมื่อ `WiFi.begin()` เชื่อมต่อ Router (Ch. 11) เสาอากาศก็ขยับไป Ch. 11 → หูหนวกต่อ Tx ที่ส่งอยู่ใน Ch. 6

**แก้ไข:** บังคับ Router ให้ใช้ Channel 6 ผ่าน Admin Panel (TP-Link: Wireless > Advanced > Channel = 6) → ทุกอุปกรณ์อยู่ใน Channel เดียวกัน

---

**ปัญหา 3 — unsigned vs signed Integer Overflow:**

```c
// BUG: uint8_t ไม่มี Sign
typedef struct {
    uint8_t buf[128];  // ← ผิด!
} csi_data_t;

// เมื่อ CSI Value = -5 (signed)
// uint8_t เก็บเป็น: (-5 + 256) = 251 ← ส่งไป Python เป็น 251

// แก้ไข:
typedef struct {
    int8_t buf[128];  // ← ถูก! -128 ถึง +127
} csi_data_t;
```

---

**ปัญหา 4 — Frame Rate Dilution (ความถี่ข้อมูลลดลงครึ่งหนึ่ง):**

เสาอากาศเดียวต้องสลับระหว่าง Receive (CSI Sniff) และ Transmit (UDP Send) ส่งผลให้:
- ก่อน: รับ CSI ได้ 30 Frame/s → Window 45 Frame = 1.5 วินาที ✓
- หลัง: รับได้เหลือ ~15 Frame/s → Window 45 Frame = 3 วินาที ✗ (Variance ลดลง 4 เท่า!)

**แก้ไข — UDP Packet Batching:**
```c
// Arduino: เก็บ 5 Frame ก่อนส่ง 1 UDP Packet
#define BATCH_SIZE 5
char batch_buffer[BATCH_SIZE * 256];
int batch_count = 0;

void csi_callback(...) {
    // เพิ่ม Frame เข้า Buffer
    strcat(batch_buffer, frame_string);
    strcat(batch_buffer, "\n");
    batch_count++;
    
    if (batch_count >= BATCH_SIZE) {
        udp.print(batch_buffer);  // ส่งครั้งเดียว
        memset(batch_buffer, 0, sizeof(batch_buffer));
        batch_count = 0;
    }
}
```

```python
# Python: แยก Multi-line Packet
def _read_loop(self):
    data, addr = self.sock.recvfrom(4096)
    lines = data.decode().split('\n')
    for line in lines:
        if line.strip():
            self._parse_line(line)  # Process ทีละ Frame
```

ผลลัพธ์: ลด UDP Transmission Overhead ลง 500% → ESP32 ใช้เวลา 95% ฟัง CSI → Frame Rate กลับมาเป็น 30Hz

---

## Phase 1.75 — Edge Compute Server & Cloudflare Global Deployment

### เป้าหมาย
ย้าย ML Inference ขึ้น Raspberry Pi 5 และเปิดให้เข้าถึง Dashboard ได้จากทั่วโลกโดยไม่ต้องเปิด Router Port

### วิธีการ
เขียน `headless_brain.py` เพื่อทำหน้าที่เป็น Unified Server ตัวเดียวที่รวม HTTP Server (ส่งหน้า Dashboard) และ WebSocket Server (Stream ข้อมูล Real-time) ไว้บน Port `8000` เดียวกัน โดยใช้ Python `asyncio` ซึ่งเป็น Single-thread Event Loop ที่สามารถรองรับ Connection หลายพันตัวพร้อมกันได้โดยไม่ต้องสร้าง Thread ใหม่ทุก Request

สำหรับการเปิดใช้งานสาธารณะ: Deploy `cloudflare/cloudflared` ใน Docker Container เพื่อสร้าง Encrypted Tunnel ระหว่าง Raspberry Pi กับ Cloudflare's Global Network ข้อดีคือไม่ต้องเปิด Port ใน Router เลย ระบบยังปลอดภัยเต็มที่เพราะ Cloudflare ทำ TLS Termination และ DDoS Protection ให้

### สถาปัตยกรรมเครือข่าย

```
อินเทอร์เน็ต
    ↓ HTTPS/WSS
cloudflare.com (TLS Termination + DDoS Protection)
    ↓ HTTP/WS (Encrypted Tunnel — ไม่ต้องเปิด Router Port)
cloudflared daemon (บน Raspberry Pi)
    ↓ localhost:8000
headless_brain.py (Python AsyncIO Server)
    ├── GET /           → ส่งไฟล์ dashboard/index.html
    ├── WebSocket /ws   → Stream ข้อมูล Real-time (15 FPS)
    └── ส่งคำสั่ง       → รับ Command จาก Dashboard
         ↕ USB Serial / UDP
    ESP32 Rx Node(s)
```

### ปัญหา 1 — 502 Bad Gateway

```yaml
# ปัญหา: Docker Container มี Network Namespace แยกจาก Host
cloudflared → "http://localhost:8000" → Container's localhost ≠ Pi's localhost

# แก้ไข: ใช้ --network host flag
docker run -d \
    --network host \          # ← บังคับ Container ใช้ Network Stack ของ Pi
    --restart unless-stopped \
    cloudflare/cloudflared:latest \
    tunnel run raspi5
```

### ปัญหา 2 — Browser Graphics Lag (ชั้น Dual Optimization)

**ต้นทาง (Backend):** จำกัด WebSocket Broadcast เป็น 15 FPS
```python
async def _broadcast_loop(self):
    while True:
        payload = build_payload(self.nodes)
        await self.broadcast_ws(payload)
        await asyncio.sleep(0.066)  # 1/15 วินาที = 15 FPS
```

**ปลายทาง (Frontend):** ปิด Chart.js Animation + ใช้ requestAnimationFrame
```javascript
// ปิด Animation เพื่อ Instant Render
chart.update('none');

// Decouple WebSocket จาก UI Thread
ws.onmessage = (e) => {
    pendingData = JSON.parse(e.data);  // แค่เก็บข้อมูล
    if (!rafScheduled) {
        requestAnimationFrame(renderFrame);  // วาด UI ตอน Browser พร้อม
        rafScheduled = true;
    }
};
```

### ปัญหา 3 — Responsive Layout พัง บน Mobile

**สาเหตุ:** CSS ของ Dashboard ถูกล็อคด้วย `height: 100vh; overflow: hidden` ซึ่งทำงานได้บน Desktop ขนาด 1920×1080 แต่เมื่อเปิดบน iPhone หรือ iPad:
- กราฟ 52 Subcarrier ถูก Clip ออกนอกหน้าจอ
- Control Card ยุบตัวเป็นแถวแนวตั้งที่แคบมาก
- ไม่มี Scroll ทำให้ข้อมูลส่วนล่างสุดมองไม่เห็นเลย

**แก้ไข:** ปรับ CSS Architecture ในสามจุดพร้อมกัน:
- เปลี่ยน `height: 100vh` → `min-height: 100vh` เพื่อให้หน้าขยายตามเนื้อหา
- เพิ่ม `overflow-x: auto` ให้กับ Chart Wrapper เพื่อให้ Scroll แนวนอนได้ในกรณีกราฟยาว
- เพิ่ม `@media (max-width: 768px)` Breakpoint เพื่อให้ Control Card เรียงตัวเป็นแถวเดียว (Column) บน Mobile แทนที่จะบีบอัดอยู่ใน Row เดียวกัน

---

### ปัญหา 4 — Multi-Device State Sync + UI ค้างรอ Backend

**สาเหตุส่วนที่ 1 (State Desync):** เมื่อผู้ใช้คนหนึ่ง (เช่น ใน iPhone) กด Disconnect ระบบจะส่งคำสั่งไป Python และ Python อัปเดต State ของตัวเอง แต่ผู้ใช้คนอื่นที่เปิด Dashboard ใน PC อีกเครื่องยังเห็น UI เก่าอยู่เพราะไม่มีการ Push State กลับมา

**สาเหตุส่วนที่ 2 (UI Freeze):** เมื่อกดปุ่ม Connect ปุ่มจะค้างอยู่ 1-2 วินาทีโดยไม่มี Feedback ใดๆ เพราะ JavaScript รอ Response กลับจาก Python ก่อนถึงจะ Update UI ซึ่งในช่วงเวลานั้น Python กำลัง Initialize PySerial Port ที่ใช้เวลาจริง

**แก้ไขส่วนที่ 1 — broadcast_config Architecture:**
```python
async def broadcast_config(self):
    # สร้าง Snapshot ของ State ปัจจุบัน
    config = {
        "type": "config",
        "tx_mode": self.tx_mode,
        "threshold": self.threshold,
        "available_ports": [p.device for p in list_ports.comports()],
        "active_serial_ports": list(self.readers.keys()),
        "active_udp_ports": [...]
    }
    # ส่งให้ทุก Client พร้อมกัน ด้วย asyncio.gather (parallel)
    if self.connected_clients:
        await asyncio.gather(*[
            client.send(json.dumps(config))
            for client in self.connected_clients
        ])
```

ทุก Action ที่เปลี่ยน State (Connect, Disconnect, เปลี่ยน Mode) จะ `await self.broadcast_config()` เสมอ ทำให้ทุก Device เห็น State เดียวกันแบบ Real-time

**แก้ไขส่วนที่ 2 — Optimistic UI Update:**
เมื่อผู้ใช้กดปุ่ม JavaScript จะ Disable และเปลี่ยน Label เป็น "กำลังเชื่อมต่อ..." ทันทีโดยไม่รอ Backend ผลคือผู้ใช้ได้รับ Feedback ภายใน 0ms แล้ว Backend ค่อยทำงานจริงอยู่เบื้องหลัง เมื่อ `broadcast_config` ส่งกลับมา UI จะอัปเดตเป็น State จริงโดยอัตโนมัติ

---

## Phase 2 — Universal Brain (USB + UDP + mDNS)

### วิธีการ
พัฒนา "Universal Firmware" (`Arduino_UDP_Receiver.ino`) ที่ทำงานสองโหมดพร้อมกัน: เมื่อรับ CSI Frame แล้วจะส่งข้อมูลเดียวกันออกทั้งทาง **USB Serial** และทาง **Wi-Fi UDP** พร้อมกัน ผู้ใช้ Flash ESP32 ครั้งเดียวแล้วใช้ได้ทั้งสองโหมดตลอดไป เพียงแค่เลือกจาก Dashboard ว่าจะรับจาก Port ไหน

ฝั่ง Backend, `headless_brain.py` ถูก Refactor ให้ `self.readers` เป็น Dictionary แทน Single Instance — สามารถ Instantiate ทั้ง `SerialReader` และ `UDPReader` พร้อมกันได้ในทีเดียว

### ปัญหา 1 — Hardcoded IP ทำให้ระบบพังเมื่อ Router รีบูต

**สาเหตุ:** Firmware เดิม Hardcode IP ของ Raspberry Pi ไว้ตรงๆ เช่น `192.168.1.8` เมื่อ Router รีบูตและ DHCP ออก IP ใหม่ให้ Pi (เช่น `192.168.1.15`) ESP32 ก็จะยิง UDP Packet ไปที่ `192.168.1.8` ซึ่งไม่มีใครฟังอยู่ ระบบพังทั้งหมดโดยไม่มี Error Message ใดๆ

### mDNS Auto-Discovery เชิงลึก

**ปัญหา:** IP Address ของ Raspberry Pi เปลี่ยนทุกครั้งที่ Router รีบูต

**mDNS (Multicast DNS) — RFC 6762:**
แทนที่จะใช้ DNS Server กลาง, mDNS ให้อุปกรณ์แต่ละตัวตอบ Query เองผ่าน Multicast Address `224.0.0.251` บน Port 5353

```cpp
// Arduino firmware
#include <ESPmDNS.h>

void setup() {
    WiFi.begin(SSID, PASSWORD);
    while (WiFi.status() != WL_CONNECTED) delay(100);
    
    // ถาม Network ว่า "OhmPatumwan.local" อยู่ที่ IP ไหน?
    while (true) {
        IPAddress serverIP = MDNS.queryHost("OhmPatumwan.local");
        if (serverIP != INADDR_NONE) {
            target_ip = serverIP.toString();
            break;
        }
        delay(2000);
    }
}
```

Raspberry Pi ต้อง Register ชื่อตัวเองก่อน:
```bash
# ติดตั้ง Avahi mDNS Daemon บน Pi
sudo apt install avahi-daemon
sudo hostnamectl set-hostname OhmPatumwan
# Pi จะตอบ OhmPatumwan.local → IP ปัจจุบันอัตโนมัติ
```

### ปัญหา 2 — Firmware Fragmentation (ต้อง Flash ใหม่ทุกครั้งที่เปลี่ยนโหมด)

**สาเหตุ:** Phase 1.75 ใช้ Firmware สำหรับ USB Serial และ Phase 1.5 ใช้ Firmware สำหรับ UDP แยกกันคนละไฟล์ ทุกครั้งที่ต้องการเปลี่ยนโหมดต้องเปิด Arduino IDE, เลือก Sketch ใหม่, รอ Compile, Flash ใหม่ ใช้เวลา 2-3 นาทีต่อครั้ง และมีความเสี่ยง Flash ผิดไฟล์

**แก้ไข:** รวม Logic ทั้งสองไว้ใน Firmware เดียว โดยใช้ `#define` Flag เพื่อ Compile ทั้งสองโหมดไว้ในตัว และส่งข้อมูลออกทุก Interface พร้อมกันในทุก CSI Callback:

```cpp
void csi_callback(void* ctx, wifi_csi_info_t* info) {
    format_csi_string(info, line_buf);  // สร้าง String ครั้งเดียว
    
    Serial.write(line_buf, len);        // → USB Serial (รับโดย Pi)
    udp.print(line_buf);                // → Wi-Fi UDP (รับโดย Pi ผ่าน Network)
}
```

ผลคือ Flash ครั้งเดียว ใช้ได้ตลอดอายุการใช้งาน ผู้ใช้เพียงเลือกจาก UI ว่าจะ Listen จาก Port ไหน

---

## Phase 3 — God Firmware & Zero-Lag Pipeline

### ปัญหา 1 — Serial Output Bottleneck

**วิเคราะห์ก่อนแก้:**
```c
// SLOW: Serial.print() ส่งทีละ Character (Blocking)
for (int i = 0; i < 52; i++) {
    Serial.print(amplitudes[i]);  // Blocking I/O call × 52
    Serial.print(",");            // เพิ่ม Overhead
}
Serial.println();
// รวม ~52 Syscall บน Hardware UART → สะสมหน่วงเวลา
```

```c
// FAST: God Firmware — Pre-format แล้ว Write ครั้งเดียว
void send_csi_data(int8_t* data, int len) {
    char buf[512];
    int pos = 0;
    for (int i = 0; i < len; i++) {
        pos += sprintf(buf + pos, "%d,", data[i]);
    }
    buf[pos-1] = '\n';  // แทน Comma สุดท้ายด้วย Newline
    Serial.write((uint8_t*)buf, pos);  // 1 Syscall เท่านั้น
}
```

### ปัญหา 2 — Pandas Hot-Path Overhead

**บริบท:** หลังจากย้าย ML มาทำงานบน Raspberry Pi 5 สังเกตว่า Dashboard เริ่ม Lag ขึ้นเรื่อยๆ ทุกครั้งที่ใช้งานนานขึ้น กราฟแสดงผลช้าลงและ State Machine ตัดสินใจล้าช้ากว่า Real-time มากขึ้นเรื่อยๆ ราวกับว่า Processing Queue กำลังสะสมแบบ Infinite

**วิเคราะห์ด้วย cProfile:**
```
function calls | cumtime | filename
───────────────────────────────────
30/s × DataFrame()    → 167ms accumulated/s ← ปัญหา!
30/s × feature_extract → 12ms
30/s × RF.predict()   → 8ms
```

```python
# SLOW: Pandas DataFrame
def extract_features_slow(history):
    df = pd.DataFrame(history)   # ← Allocate + Garbage = 167ms/s
    return [df.var().mean(), df.std().mean(), ...]

# FAST: Raw NumPy
def extract_features_np(history_array):
    # history_array คือ numpy array (45, 52) ที่ถูก Pre-allocate แล้ว
    means = np.mean(history_array, axis=1)   # Vector Operation (C-speed)
    return [np.var(means), np.std(means), np.mean(means), 
            np.mean(np.diff(means)), np.ptp(means)]
```

### ปัญหา 3 — Browser Render Jank ที่ 30Hz

**สาเหตุ:** เดิม WebSocket ส่ง JSON 30 ครั้ง/วินาที และทุกครั้งที่ได้รับ JavaScript จะเรียก `chart.update()` ทันที Chart.js จะคำนวณ Bezier Curve Animation ใหม่ทั้ง Series ทุก Call ซึ่งใช้ CPU มาก บน Desktop ยังพอรับได้ แต่บน iPad หรือ PC ที่เปิด Tab อื่นด้วย จะเห็น Graph กระตุก (Jank) ชัดเจน

**แก้ไข — requestAnimationFrame Buffer:**
แทนที่จะ Render ทันทีที่ได้รับ Data, JavaScript จะเก็บข้อมูลล่าสุดไว้ใน `pendingData` ก่อน แล้วค่อย Render ตอนที่ Browser พร้อม (ช่วง vsync) ผ่าน `requestAnimationFrame` ซึ่งเป็น Browser API ที่ซิงค์กับ Hardware Display Refresh Rate (60Hz) พอดี ทำให้ Chart ไม่เคย Render บ่อยกว่าที่หน้าจอจะแสดงได้

### ปัญหา 4 — JSON Serialization Crash (Sporadic Backend Crash)

**สาเหตุ:** Backend ล่มโดยไม่มีสัญญาณเตือนล่วงหน้า Systemd Restart ทุกครั้ง ทำให้ Dashboard Disconnect และ Connect ใหม่ตลอด เมื่อดู Log พบ:
```
TypeError: Object of type int32 is not JSON serializable
```

ปัญหาคือ `scikit-learn`'s `model.predict()` คืนค่าเป็น **NumPy `int32`** ไม่ใช่ Python `int` ทั่วไป Python's `json.dumps()` รู้จักเฉพาะ Native Python types เท่านั้น (`int`, `float`, `str`, `list`) ไม่รู้จัก NumPy Scalar Types ซึ่งเป็น C-wrapper ที่ต่างออกไป

```python
# Bug
prediction = model.predict([features])  # Return: numpy.int32
json.dumps({"state": prediction[0]})    # TypeError!

# Fix: Explicit Python int cast
raw_pred = int(model.predict([features])[0])  # Convert numpy.int32 → Python int
```

### ปัญหา 5 — Chart.js Memory Leak (RAM เพิ่มขึ้นเรื่อยๆ ตามเวลา)

**สาเหตุ:** เมื่อเปิด Dashboard ทิ้งไว้หลายชั่วโมง RAM การใช้งาน Browser ค่อยๆ เพิ่มขึ้นเรื่อยๆ จน Browser เริ่มทำ Garbage Collection (GC) บ่อยขึ้น ทำให้ Graph กระตุกเป็นช่วงๆ

สาเหตุอยู่ที่ JavaScript บรรทัดนี้:
```javascript
this.rawChart.data.datasets[0].data = newAmplitudes; // ← สร้าง Array ใหม่ทุก Frame
```

ทุก 66ms (15 FPS) JavaScript สร้าง Array ใหม่ขนาด 52 ตัว แล้ว Assign ให้ Chart.js Chart.js ตรวจพบว่า Object Reference เปลี่ยน จึงสร้าง Internal `_meta` Objects ใหม่ 52 ตัวสำหรับการ Render ส่วน Array เก่าถูกทิ้งรอ GC เก็บ ที่ 15 FPS เท่ากับสร้างและทิ้ง 780 Object/วินาที ทำงานต่อเนื่อง 8 ชั่วโมง = Object หลายล้านตัวที่ GC ต้องตามเก็บ

```javascript
// FIX: Mutate In-Place (Zero Allocation)
// ไม่สร้าง Array ใหม่ — เขียนทับของเดิมที่ Address เดิม
const rawData = this.rawChart.data.datasets[0].data;
for (let i = 0; i < data.amplitudes.length; i++) {
    rawData[i] = data.amplitudes[i];  // เขียนทับค่า ไม่ได้เปลี่ยน Object
}
// Chart.js เห็น Reference เดิม → ใช้ Internal Objects เดิม → GC ไม่มีอะไรทำเลย
```

---

## Phase 4 — Multi-Node Architecture & Stability

### เป้าหมาย
ขยายระบบจากห้องเดียวเป็นทั้งบ้าน รองรับ ESP32 Rx หลายตัวพร้อมกัน แต่ละตัวอยู่ในห้องต่างกัน (เช่น ห้องนั่งเล่น + ห้องน้ำ) แสดงผลใน Dashboard เป็น Block อิสระของแต่ละห้อง

### การออกแบบ Data Model สำหรับ Multi-Node

**สถาปัตยกรรมเดิม (Phase 3):** ระบบมี `NodeState` Object เดียว — ถ้า ESP32 สองตัวส่งข้อมูลมาพร้อมกัน ข้อมูลจะเขียนทับกันเองใน Object เดียวกัน

**สถาปัตยกรรมใหม่ (Phase 4):** เปลี่ยนเป็น Dictionary ที่ Key คือ Unique Location ID ซึ่งสร้างจาก Interface + ชื่อห้อง ทุกการดำเนินการ (ดึง Feature, Run ML, ส่ง WebSocket) ทำงานบน `NodeState` ของแต่ละห้องแยกกัน

```python
# ก่อน Phase 4: Single Instance
self.node = NodeState()  # มีแค่ 1 Node — ถ้ามีสอง ESP32 ข้อมูลชนกัน

# หลัง Phase 4: Dictionary of Nodes
self.nodes: dict[str, NodeState] = {}
# Key = unique location ID, e.g. "[/dev/ttyUSB0] Bath Room"
#                                   "[/dev/ttyUSB1] Living Room"
# Value = NodeState object แยกกันสมบูรณ์ (ไม่ Share State)
```

```python
class NodeState:
    def __init__(self):
        self.history = deque(maxlen=45)             # 1.5 วินาทีของ Raw Data
        self.prediction_history = deque(maxlen=15)  # Temporal Smoothing Buffer
        self.frame_count = 0
        self._processing = False                    # Thread Safety Lock — ป้องกัน Race Condition
        self.potential_fall_time = 0
        self.last_line_alert_time = 0
        self.current_state = 0                      # 0=STATIC, 1=MOVE, 2=FALL
        self.last_variance = 0.0
        self.last_seen = time.time()                # ใช้ตรวจจับ Timeout (>5s = Node ตัดการเชื่อมต่อ)
        self.threshold = THRESHOLD                  # ← Per-Node Threshold (Phase 4 ใหม่)
```

### ปัญหา 1 — Data Merging (สอง ESP32 ข้อมูลรวมกันเป็น Block เดียว)

**สาเหตุ:** ESP32 ทั้งสองตัวถูก Flash ด้วย Firmware เดียวกัน ซึ่งในโค้ด Arduino มีการกำหนด `location_name = "Bath Room"` ไว้แบบ Hardcode เหมือนกันทุกตัว เมื่อ Python ได้รับข้อมูลจากทั้งสองตัว ก็จะ Map ทั้งคู่ไปยัง Dictionary Key `"Bath Room"` เดียวกัน ข้อมูลของห้องนึงจึงเขียนทับข้อมูลอีกห้องทุก Frame

**แก้ไข — Interface Prefix Injection:**
แทนที่จะแก้ Arduino Firmware (ซึ่งต้องการ Flash ใหม่ทุกตัว), Python Backend ดักจับ Location String และเพิ่ม Prefix ของ Physical Interface ไว้ข้างหน้าโดยอัตโนมัติ:

```python
def data_received(self, amplitudes, rssi, location_name="Unknown", reader_id=None):
    if reader_id:
        # เพิ่ม Port ID เป็น Prefix ถ้ายังไม่มี
        if not location_name.startswith(f"[{reader_id}]"):
            location_name = f"[{reader_id}] {location_name}"
    # ตอนนี้: "[/dev/ttyUSB0] Bath Room" ≠ "[/dev/ttyUSB1] Bath Room"
```

ผลลัพธ์: ไม่ต้อง Re-flash ESP32 เลย แค่เสียบ Port ต่างกันก็ได้ Location ID ต่างกันทันที

### ปัญหา 2 — Zombie Chart (กราฟวาดข้อมูลผิดห้องหลัง Reconnect)

**สาเหตุ:** เมื่อ ESP32 ตัดการเชื่อมต่อ JavaScript จะลบ HTML Block ของห้องนั้นออก แต่ลืมทำลาย Chart.js Instance ที่อยู่ใน Memory เมื่อ ESP32 เชื่อมต่อกลับมา JavaScript สร้าง `<canvas>` ใหม่ แต่ Chart.js ยังมี Context เก่าที่ชี้ไปที่ Canvas เก่า (ที่ถูกลบไปแล้ว) ข้อมูลใหม่จึงไปวาดบน Internal State ที่ Corrupt ทำให้กราฟวาดเส้นไปยังจุดพิกัดเดิมที่ไม่มีอยู่บนหน้าจอแล้ว

**แก้ไข — NodeCard Class with destroy() Method:**
ห่อ HTML Rendering ไว้ใน JavaScript Class และบังคับให้ Cleanup ก่อนทำลาย DOM:

```javascript
class NodeCard {
    destroy() {
        // ต้องเรียกก่อน removeChild เสมอ!
        if (this.varianceChart) this.varianceChart.destroy(); // ← คืน GPU Context
        if (this.rawChart) this.rawChart.destroy();           // ← คืน GPU Context
        if (this.container?.parentNode) {
            this.container.parentNode.removeChild(this.container); // ลบ HTML
        }
    }
}

// เมื่อ ESP32 ตัดการเชื่อมต่อ:
activeNodes[loc].destroy();  // ← เรียก destroy() ก่อน
delete activeNodes[loc];     // ← แล้วค่อยลบออกจาก Dictionary
```

### ปัญหา 3 — ESP32 ล่มจาก PING Flooding

**บริบท:** หลัง Phase 3 มีการเพิ่ม Ping Loop เข้าไปใน `headless_brain.py` เพื่อส่ง UDP Packet ไปกระตุ้น Router ให้ส่งคลื่น Wi-Fi ออกมาสม่ำเสมอ (เพื่อให้ Home Router TX Mode ทำงานได้) โดยตั้งใจส่งไปที่ IP ของ ESP32 โดยตรง ซึ่งดูสมเหตุสมผลในตอนนั้น

**ปัญหาที่เกิดขึ้นจริง:** หลังใช้งานไป 30-60 นาที ESP32 เริ่มแสดง Lag ชัดขึ้นเรื่อยๆ (ค่า Variance อัปเดตช้าลง) และในที่สุด Block ก็หายออกจาก Dashboard เอง เมื่อสังเกตพฤติกรรมพบว่า ESP32 กำลัง Reboot ตัวเองซ้ำๆ

**สาเหตุลึก:** ESP32 ได้รับ UDP String ว่า `"PING"` จาก Pi ในอัตรา **10 Packet/วินาที** ทุก Packet ที่รับมา ESP32 ต้อง:
1. Allocate Buffer สำหรับ UDP Payload
2. Parse String จาก Buffer
3. ตรวจสอบ Command
4. Free Buffer

ESP32 มี Heap RAM ขนาดเล็กมาก (ไม่กี่ร้อย KB) การ Allocate และ Free แบบ Rapid-fire นี้สร้าง Heap Fragmentation — คือ RAM มีอยู่แต่กระจัดกระจายเป็นชิ้นเล็กชิ้นน้อยไม่ติดกัน ทำให้ Allocate Block ใหม่ไม่ได้แม้ Free Memory รวมจะยังพอ → ล่ม

**ก่อนแก้ — Direct PING ไปที่ ESP32:**
```python
# Backend ส่ง "PING" ไปที่ ESP32 IP โดยตรง 10 ครั้ง/วินาที
ping_sock.sendto(b"PING", (esp32_ip, 5000))
# ESP32 ต้องรับและ Parse ทุก Packet → Heap Fragmentation → Crash
```

**หลังแก้ — Subnet Broadcast ไปที่ Dummy Port:**
```python
# ส่ง Broadcast ไป Subnet ทั้งหมดบน Port 5001 (ไม่มีใคร Listen)
ping_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
ping_sock.sendto(b"ROUTER_STIMULUS", ('255.255.255.255', 5001))

# Router ได้รับ → Re-broadcast คลื่น OFDM → ESP32 รับ CSI ได้
# แต่ ESP32 ไม่ได้รับ PING โดยตรง → ไม่ต้อง Parse อะไรเลย
```

### ปัญหา 4 — UDP Mode Blindness (ต้องสลับปุ่มเพื่อให้ ESP32 เริ่มส่งข้อมูล)

**สาเหตุ:** เมื่อผู้ใช้กดปุ่ม Connect UDP ใน Dashboard Python จะเรียก `udp_reader.send_command("MODE_ROUTER")` เพื่อบอก ESP32 ว่าให้ Sniff คลื่นจาก Router แต่ `send_command()` ต้องการ IP ของ ESP32 ในการส่ง UDP Packet ซึ่ง Python จะ**ยังไม่รู้** IP นั้นเลยเพราะ ESP32 ยังไม่เคยส่งข้อมูลมาเลยสักครั้ง (มันรอคำสั่งก่อนถึงจะส่ง, แต่ Pi รอ IP ก่อนถึงจะส่งคำสั่ง — Deadlock!)

ผลคือ: Mode ถูก Set ไว้ใน Python แต่ ESP32 ไม่รู้ — ต้องให้ผู้ใช้สลับปุ่มกลับไปกลับมาเพื่อบังคับ Retry ซึ่งทำให้ ESP32 ส่ง Packet มาก่อน แล้ว Pi ถึงจะรู้ IP แล้วส่งคำสั่งได้

**แก้ไข — Subnet Broadcast ทำลาย Deadlock:**
แทนที่จะรอ IP, เปลี่ยน `send_command()` ให้ Broadcast คำสั่งไปทั้ง Subnet พร้อมกัน ทุก ESP32 บน Network นั้นจะได้รับคำสั่งและ Configure ตัวเองทันที โดยไม่ต้องมี Handshake ล่วงหน้า

```python
# udp_reader.py - ก่อน:
def send_command(self, cmd):
    if self.last_client_addr:          # ← Deadlock! รอ ESP32 ส่งมาก่อนถึงรู้ IP
        self.sock.sendto(cmd, self.last_client_addr)

# udp_reader.py - หลัง:
def send_command(self, cmd):
    # 1. ส่งไปยัง IP ที่รู้จักแล้ว (ถ้ามี) — สำหรับ Update หลังจากเชื่อมต่อแล้ว
    for addr in self.client_addrs:
        self.sock.sendto(cmd.encode(), addr)
    
    # 2. Subnet Broadcast — ทำลาย Deadlock สำหรับ ESP32 ที่ยังไม่เคย Reply
    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    self.sock.sendto(cmd.encode(), ('255.255.255.255', self.port))
    # ← ทุก ESP32 บน Network ได้รับและ Configure ตัวเองทันที
```

### ปัญหา 5 — Variance Graph หายเมื่อมีการเคลื่อนไหวรุนแรง

**สาเหตุ:** Chart.js Y-Axis ถูกกำหนดด้วย `max: 20` แบบ Hardcode เมื่อคน Variance สูงกว่า 20 (เช่น การล้มรุนแรงอาจได้ถึง 50-80) เส้นกราฟจะถูก Render ออกนอกขอบบน Chart ทำให้มองไม่เห็นเลย ผู้ใช้เห็นกราฟเส้นหายไปทันทีที่เกิดการเคลื่อนไหวรุนแรง ซึ่งเป็นช่วงเวลาสำคัญที่สุดที่ต้องดูกราฟ

**แก้ไข:** เปลี่ยนจาก Hard Ceiling เป็น Suggested Ceiling
```javascript
// ก่อน: กำหนดแน่นอน — ถ้า Variance เกิน 20 กราฟหาย
scales: { y: { min: 0, max: 20 } }

// หลัง: แนะนำ Ceiling — Chart.js จะขยาย Scale ขึ้นอัตโนมัติถ้าจำเป็น
scales: { y: { min: 0, suggestedMax: 20 } }
// ช่วง Static: Y-axis = 0-20 (ดูสะอาด)
// ช่วงล้ม: Y-axis ขยายเป็น 0-80 อัตโนมัติ (เห็นครบ)
```

### ปัญหา 6 — Global Threshold บังคับใช้กับทุกห้องเท่ากัน

**สาเหตุ:** `self.threshold` เป็น Class-level Variable ของ `HeadlessBrain` ตัวเดียว ใช้กับทุก Node ใน `self.nodes` เหมือนกันหมด ปัญหาคือแต่ละห้องมีสภาพแวดล้อมทางฟิสิกส์ต่างกันมาก:
- ห้องน้ำเล็ก ผนัง Tile สะท้อนคลื่นแรง → Baseline Variance สูงอยู่แล้ว ต้องการ Threshold สูง
- ห้องนั่งเล่นกว้าง มีเฟอร์นิเจอร์ดูดซับคลื่น → Variance ต่ำกว่า ต้องการ Threshold ต่ำ

ถ้าตั้ง Threshold เดียวให้ทั้งบ้าน ต้องเลือกระหว่าง False Positive สูงในห้องหนึ่ง หรือ Miss Rate สูงในอีกห้องหนึ่ง

**แก้ไข — ย้าย threshold เข้า NodeState:**
```python
# ก่อน: Shared threshold
if variance < self.threshold:  # ← ทุก Node ใช้ค่าเดียวกัน
    raw_pred = 0

# หลัง: Per-node threshold
if variance < node.threshold:  # ← แต่ละ Node มีค่าของตัวเอง
    raw_pred = 0
```

Frontend ส่ง `node_id` มาพร้อมกับค่า Threshold ใหม่ทุกครั้งที่ผู้ใช้ขยับ Slider:
```python
if data.get("command") == "set_threshold":
    node_id = data.get("node_id")
    if node_id and node_id in self.nodes:
        self.nodes[node_id].threshold = float(data.get("value"))  # อัปเดตเฉพาะห้องนั้น
```

### ปัญหา 7 — USB Hot-Plug Detection

**สาเหตุ:** `list_ports.comports()` ถูกเรียกใช้เพียงครั้งเดียวตอน Dashboard โหลดขึ้นมาครั้งแรก หลังจากนั้นไม่มี Mechanism ใดที่จะ Re-scan USB Ports โดยอัตโนมัติ ผู้ใช้พบว่าต้องเสียบ USB ตัวแรก (`/dev/ttyAMA10`) ก่อน ซึ่งไปทำให้เกิด Event ที่ Backend ตอบสนองและส่ง `broadcast_config()` กลับมา — ซึ่งโดยบังเอิญทำให้ List อัปเดต เป็น "Trick" ที่ผู้ใช้ค้นพบเอง ไม่ใช่ Feature ที่ตั้งใจทำ

**แก้ไข — Background Polling Thread:**
เพิ่ม Thread แยกต่างหากที่รันตลอดเวลา โดย Compare รายการ Port ปัจจุบันกับ Snapshot ก่อนหน้า ถ้าต่างกัน (เสียบหรือถอด USB) ก็ Trigger `broadcast_config()` ทันที

ความท้าทายคือ `broadcast_config()` เป็น `async` Coroutine ที่ต้องรันใน AsyncIO Event Loop แต่ Polling Thread นี้เป็น Regular Thread ที่ไม่มี Event Loop จึงต้องใช้ `asyncio.run_coroutine_threadsafe()` เพื่อส่ง Coroutine เข้าไปรันใน Loop ของ Main Thread:

```python
def _poll_com_ports(self):
    def _poll():
        last_ports = []
        while True:
            current_ports = [p.device for p in serial.tools.list_ports.comports()]
            
            if current_ports != last_ports:  # มีการเปลี่ยนแปลง
                last_ports = current_ports
                if self.loop and self.loop.is_running():
                    # ส่ง Coroutine จาก Regular Thread เข้าสู่ AsyncIO Loop อย่างปลอดภัย
                    asyncio.run_coroutine_threadsafe(
                        self.broadcast_config(),
                        self.loop
                    )
            time.sleep(2)  # ตรวจทุก 2 วินาที
    
    threading.Thread(target=_poll, daemon=True).start()  # daemon=True ตายพร้อม Main Process
```

---

## สรุปบทเรียนสำคัญ

| # | บทเรียน | ผลกระทบ |
|---|---|---|
| 1 | **ฟิสิกส์มาก่อน** — Channel, Line-of-Sight, และ Antenna ต้อง Align ก่อนแก้ Code | Block งานได้หลายวัน |
| 2 | **`int8_t` ไม่ใช่ `uint8_t`** สำหรับ CSI Buffer | ค่า Amplitude ผิด 180 องศา |
| 3 | **ห้าม Block asyncio Loop** — ใช้ `threading.Thread(daemon=True)` เสมอสำหรับ I/O | Dashboard ค้าง |
| 4 | **Chart.js ต้องการ `destroy()`** ก่อนลบ DOM Node เสมอ | Zombie Chart / Memory Leak |
| 5 | **อย่าส่ง UDP String ตรงไป ESP32 อย่างต่อเนื่อง** | Heap Fragmentation → Crash |
| 6 | **Subnet Broadcast** (`255.255.255.255`) ดีกว่า Direct-IP สำหรับ Discovery | Zero-config Connection |
| 7 | **`suggestedMax` แทน `max`** ใน Chart.js สำหรับ Dynamic Range | Graph หายไปเมื่อ Variance สูง |
| 8 | **Docker ต้องการ `--network host`** เพื่อเข้าถึง Host's localhost | 502 Bad Gateway |
| 9 | **ไม่ใช้ Pandas ใน Real-time Loop** — ใช้ NumPy Arrays โดยตรง | ลด Latency 15× |
| 10 | **"Dedicated Node" Mode** ต้องการ TX ESP32 แยกต่างหากเสมอ — ถ้าไม่มีให้ใช้ "Home Router" | Node หายจาก Dashboard |

---

## สถานะระบบปัจจุบัน (Phase 4)

| Feature | สถานะ |
|---|---|
| Multi-room Monitoring | **ใช้งานได้** (Living Room + Bathroom ทดสอบแล้ว) |
| Wireless UDP Mode | **ใช้งานได้** + Subnet Broadcast Auto-discovery |
| USB Serial Mode | **ใช้งานได้** + Hot-plug Detection ทุก 2 วินาที |
| Per-room AI Threshold | **ใช้งานได้** |
| LINE Emergency Alert | **ใช้งานได้** (Cooldown 60 วินาที) |
| Global Dashboard | **ใช้งานได้** ที่ `https://csi.ohmpatumwan.com` |
| Systemd Auto-start | **ใช้งานได้** (`sentry.service` บน Raspberry Pi 5) |

---
*รายงานนี้จัดทำจาก Engineering Log — มิถุนายน 2569*
