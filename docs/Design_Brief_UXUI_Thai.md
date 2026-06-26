# Sentry Dashboard — Design Brief สำหรับทีม UX/UI
**เอกสารนี้จัดทำสำหรับ:** ทีม Designer  
**วัตถุประสงค์:** อัปเดต Design ของ Dashboard ให้สอดคล้องกับ Feature ที่พัฒนาแล้ว และ Feedback ที่ได้รับ  
**รูปแบบ:** นำ Design ที่ทำไว้แล้วมาแทรก Feature เพิ่มเข้าไป

---

## 1. ภาพรวม — Dashboard คืออะไร?

Sentry Dashboard คือหน้า Web App ที่แสดงผลระบบตรวจจับการล้มแบบ Real-time  
เปิดได้จากทุกอุปกรณ์ผ่าน `https://csi.ohmpatumwan.com`

**ผู้ใช้งานหลัก:** ผู้ดูแลผู้สูงอายุ, นักวิจัย, ทีมเทคนิค  
**Platform:** Web Browser (Desktop + Mobile)  
**สถานะ Design ปัจจุบัน:** มี Design Mockup แล้ว (ดูรูปที่ส่งมา)

---

## 2. สิ่งที่มีอยู่แล้วใน Code (Backend พร้อมแล้ว)

> **สำคัญ:** Feature ด้านล่างนี้มี Logic ใน Code แล้วทั้งหมด — ต้องการแค่ **Design** และ **UI Component** เท่านั้น ไม่ต้องรอ Dev

### 2.1 การเชื่อมต่อฮาร์ดแวร์ (Hardware Connection)
ระบบรองรับการเชื่อมต่อ 2 ประเภท:

| ประเภท | คำอธิบาย | ตัวอย่าง |
|---|---|---|
| **COM Port (USB Serial)** | เสียบสาย USB จาก ESP32 ตรงเข้า Raspberry Pi | `/dev/ttyUSB0`, `/dev/ttyAMA10` |
| **Wireless UDP** | ESP32 ส่งข้อมูลผ่าน Wi-Fi มายัง Pi | Port 5000 |

ระบบ**เลือกพร้อมกันได้หลายพอร์ต** (Multi-RX) เช่น เสียบ USB 2 เส้น + เปิด UDP พร้อมกัน

### 2.2 Transmitter Target (แหล่งกำเนิดคลื่น Wi-Fi)
ผู้ใช้เลือกได้ว่าจะให้ ESP32 รับคลื่นจากไหน:

| Mode | คำอธิบาย | ใช้เมื่อไหร่ |
|---|---|---|
| **Dedicated Node (TX ESP32)** | มี ESP32 อีกตัวทำหน้าที่ส่งคลื่นโดยเฉพาะ | มีอุปกรณ์ครบ 2 ตัว |
| **Home Router** | ใช้คลื่น Wi-Fi ของ Router ในบ้านที่มีอยู่แล้ว | ใช้งานปกติ (แนะนำ) |

> ⚠️ **หมายเหตุสำคัญสำหรับ Designer:** ถ้าผู้ใช้เลือก "Dedicated Node" แต่ไม่ได้เปิด ESP32 TX ไว้ กราฟจะหายไป เพราะไม่มีคลื่นส่งมา — ควรมี Tooltip หรือ Warning แจ้งผู้ใช้

### 2.3 Sensitivity Threshold (ระดับความไว)
- ทุก Location Block มี Slider อิสระของตัวเอง
- ยิ่ง Threshold ต่ำ = ตรวจจับการเคลื่อนไหวเล็กน้อยได้ (ไวมาก)
- ยิ่ง Threshold สูง = ต้องมีการเคลื่อนไหวมากถึงจะ Trigger (ป้องกัน False Alarm)

### 2.4 กราฟที่แสดงผล
**กราฟ 1 — Live Motion Index (Variance):**
- เส้น **สีน้ำเงิน**: ค่า Variance ของคลื่น Wi-Fi แบบ Real-time
- เส้น **สีเหลือง (Dashed)**: เส้น Threshold — ถ้าเส้นสีน้ำเงินอยู่เหนือเส้นนี้ = มีการเคลื่อนไหว

**กราฟ 2 — Raw CSI Subcarriers (Snapshot):**
- แสดง 52 ความถี่ย่อยของสัญญาณ Wi-Fi ณ ขณะนั้น
- ใช้ดูว่าสัญญาณกำลังทำงานปกติหรือเปล่า

### 2.5 Location Block (การ์ดแต่ละห้อง)
- **เพิ่มอัตโนมัติ** เมื่อมีการเชื่อมต่อ ESP32 ใหม่
- **หายอัตโนมัติ** เมื่อ ESP32 ตัดการเชื่อมต่อ (หรือไม่มีสัญญาณ 5 วินาที)
- แต่ละ Block แยกอิสระ — ห้อง A กับ ห้อง B มีกราฟและ Threshold ของตัวเอง

---

## 3. Feedback จาก Review — สิ่งที่ต้องแก้ไข / เพิ่มเติม

### ✅ 3.1 แก้ Typo ใน Section "สถิติเซสชั่นนี้"
**ปัญหา:** คำว่า "ความเคลื่อนไหว" พิมพ์ตก  
**Action:** แก้ไขตัวสะกดให้ถูกต้อง

---

### ✅ 3.2 เพิ่ม Tooltip / คำอธิบายปุ่มจำลองสถานการณ์
**ปัญหา:** ผู้ใช้ไม่เข้าใจว่าปุ่มจำลองสถานการณ์ (ว่าง / ทำสิ่งเดิน / ตรวจพบการล้ม) มีไว้ทำอะไร นอกจากทำให้กราฟและสถานะเปลี่ยน

**วัตถุประสงค์จริงของปุ่มจำลอง:**
1. **ทดสอบระบบแจ้งเตือน LINE** — กด "ตรวจพบการล้ม" เพื่อทดสอบว่า LINE ส่งมาถึงผู้ดูแลหรือเปล่า
2. **Demo ให้ผู้ที่ไม่ได้อยู่ในพื้นที่ดู** — ถ้าต้อง Present ระบบโดยไม่มีคนล้มจริง
3. **Calibration** — ดูว่า Threshold ตั้งไว้ถูกหรือเปล่าโดยไม่ต้องเคลื่อนไหวจริง

**Action:** เพิ่ม Tooltip หรือ Description Text เล็กๆ ใต้ปุ่ม เช่น:
> *"ใช้สำหรับทดสอบระบบและ Demo — จะส่ง LINE Alert ให้ผู้ดูแลจริง"*

---

### ✅ 3.3 Layout — การเชื่อมต่อและ Transmitter อยู่ในระดับเดียวกับ Threshold ได้

**Feedback:** Layout 2 ส่วนนี้ (เลือก Connection + เลือก Transmitter) วางอยู่ในระดับเดียวกับ Threshold ได้  
คือไม่จำเป็นต้องแยก Section ต่างหาก สามารถรวมอยู่ใน Panel เดียวกันได้

**Action:** ปรับ Layout ให้ Control Panel 3 อย่างนี้อยู่ในแถวเดียวกัน:
```
┌─────────────────────────────────────────────┐
│  การเชื่อมต่อ  │  Transmitter  │  Threshold  │
│  [COM / UDP]   │  [TX / Router]│   Slider    │
└─────────────────────────────────────────────┘
```

---

### ✅ 3.4 Quick Guide — ต้องมีในหน้าหลัก

**ปัญหา:** Design ขาด Section นำทางผู้ใช้ครั้งแรก  
**ใน Code มีอยู่แล้ว** — Quick Guide ปัจจุบัน (ภาษาอังกฤษ):
1. Select your ESP32 USB port and click Connect.
2. Adjust Threshold to tune sensitivity.
3. For best accuracy, ensure RX and TX antennas have clear line of sight.

**Action:** ออกแบบ Quick Guide Component ในภาษาไทย (รายละเอียดดูหัวข้อ 4.1)

---

### ✅ 3.5 เพิ่มปุ่ม Dark / Light Mode Toggle

**หมายเหตุ:** Design ที่ส่งมา (รูปในไฟล์) มีปุ่ม Dark / Light อยู่แล้วที่มุมบน — ดีมาก!  
ใน Code ปัจจุบัน **ยังไม่มี Logic** สำหรับ Light Mode  
**Action ของ Designer:** กำหนด Color Token สำหรับ Light Mode ด้วย ทีม Dev จะนำไปใส่ CSS Variable

```
Dark Mode (ปัจจุบัน):
  Background: #0a0a1a
  Primary:    #00d2ff
  Text:       #e0e0ff

Light Mode (ต้องการ):
  Background: #f0f4ff  ← ควรเป็นอะไร?
  Primary:    ?        ← ให้ Designer กำหนด
  Text:       ?
```

---

### ✅ 3.6 ปุ่มสลับภาษา TH / EN

**หมายเหตุ:** ปุ่ม TH / EN ก็อยู่ใน Design แล้ว — ดีมาก!  
**หลักการสำหรับการแปลภาษา:**

| คำภาษาไทย | ทับศัพท์อังกฤษ (ไม่ต้องแปล) |
|---|---|
| ค่า Variance | Variance |
| Subcarrier | Subcarrier |
| Threshold | Threshold |
| UDP | UDP |
| COM Port | COM Port |
| Dashboard | Dashboard |
| Real-time | Real-time |
| Session | Session |

คำที่ **ควรแปลเป็นไทย** เมื่อสลับภาษา:

| ภาษาอังกฤษ | ภาษาไทย |
|---|---|
| Current Status | สถานะปัจจุบัน |
| Hardware Connection | การเชื่อมต่อฮาร์ดแวร์ |
| Transmitter Target | แหล่งสัญญาณ |
| Dedicated Node | โหนดส่งสัญญาณโดยตรง |
| Home Router | เราเตอร์ที่บ้าน |
| Quick Guide | คู่มือเริ่มต้น |
| Connect / Disconnect | เชื่อมต่อ / ยกเลิก |
| Session Statistics | สถิติเซสชั่นนี้ |
| Fall Detected | ตรวจพบการล้ม |
| Movement | มีการเคลื่อนไหว |
| Static | หยุดนิ่ง |
| Save Data | บันทึกข้อมูล |

**ตำแหน่ง Toggle:** ปุ่มทั้งสอง (Dark/Light + TH/EN) อยู่ **ด้านบนขวา** ของหน้า — รูปแบบ Toggle แบบ Pill Switch ตามที่ Design ไว้แล้ว

---

## 4. Design Spec — Component ที่ต้องออกแบบ

### 4.1 Quick Guide Card
ควรอยู่ใน Control Panel แถบซ้าย (หรือ Collapsible Panel)

```
┌──────────────────────────────┐
│  คู่มือเริ่มต้นใช้งาน         │
│                              │
│  1. เลือก COM Port หรือ UDP  │
│     แล้วกด "เชื่อมต่อ"        │
│                              │
│  2. เลือก Transmitter:       │
│     • เราเตอร์ที่บ้าน (แนะนำ) │
│     • โหนด ESP32 แยกต่างหาก  │
│                              │
│  3. ปรับ Threshold ของแต่ละห้อง│
│     ต่ำ = ไวมาก | สูง = ทนนอยส์│
│                              │
│  4. ตรวจสอบให้เสาอากาศ RX–TX  │
│     มองเห็นกันโดยตรง          │
└──────────────────────────────┘
```

### 4.2 Connection Selector (การเลือกประเภทการเชื่อมต่อ)
ออกแบบ Dropdown หรือ Toggle สำหรับ:
- **ประเภท:** COM Port (USB) หรือ Wireless UDP
- **พอร์ต:** แสดง List ของ Port ที่มี (เช่น `/dev/ttyUSB0`) พร้อมปุ่ม Connect/Disconnect แต่ละตัว

```
การเชื่อมต่ออุปกรณ์
├── Wireless UDP (Port 5000) ── [เชื่อมต่อ]
├── /dev/ttyUSB0             ── [เชื่อมต่อ]
└── /dev/ttyAMA10            ── [ยกเลิก ●]
```

### 4.3 Transmitter Target Toggle
Toggle Pill แบบเดียวกับ Dark/Light Mode:
```
[ โหนด ESP32 ]  [ เราเตอร์ที่บ้าน ← Active ]
```
มี Tooltip อธิบายว่าแต่ละโหมดต่างกันอย่างไร

### 4.4 Location Block (Node Card) — Per-Room
แต่ละห้องจะแสดง Card ที่ประกอบด้วย:

```
┌─────────────────────────────────────────┐
│  Location: ห้องนอน  [/dev/ttyUSB0]       │
│                                         │
│  ┌──────────────┐  ┌──────────────────┐ │
│  │   STATIC     │  │  Variance: 0.42  │ │
│  │  LIVE INFER  │  │ Sensitivity ─────┤ │
│  └──────────────┘  │ [● Slider ] 2.0  │ │
│                    └──────────────────┘ │
│  ┌──────────────────────────────────┐   │
│  │  Live Motion Index (Variance)   │   │
│  │  [กราฟเส้น Real-time]           │   │
│  └──────────────────────────────────┘   │
│  ┌──────────────────────────────────┐   │
│  │  Raw CSI Subcarriers Snapshot   │   │
│  │  [กราฟเส้น 52 Subcarrier]       │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### 4.5 สถิติเซสชั่น (Session Statistics)
แสดงในกล่องข้างกราฟ CSI (ตาม Design เดิม) ประกอบด้วย:

| ค่าที่แสดง | ตัวเลขตัวอย่าง | สีที่แนะนำ |
|---|---|---|
| ครั้งที่ล้ม | 0 | สีแดง |
| ความเคลื่อนไหว | 0 | สีส้ม |
| Hz อัตราสัญญาณ | 30 | สีขาว |
| Subcarriers | 52 | สีขาว |
| สถานะระบบ | ระบบทำงานปกติ | สีเขียว |

> ⚠️ **แก้ไข Typo:** "ความเคลื่อนไหว" — ตรวจสอบการสะกดในทุก Component

---

## 5. ลำดับความสำคัญในการอัปเดต

| ลำดับ | รายการ | ความยาก | ความสำคัญ |
|---|---|---|---|
| 1 | แก้ Typo สถิติ | ง่าย | สูง |
| 2 | Layout Control Panel (Connection + TX + Threshold ในแถวเดียว) | ปานกลาง | สูง |
| 3 | Quick Guide Component | ง่าย | สูง |
| 4 | Tooltip ปุ่มจำลองสถานการณ์ | ง่าย | กลาง |
| 5 | Dark/Light Color Token | ปานกลาง | กลาง |
| 6 | Thai/EN Label Mapping | ปานกลาง | กลาง |
| 7 | Connection Selector Design | ยาก | ต้องทำ |
| 8 | Dark/Light + TH/EN Toggle Position | ง่าย | เสร็จแล้วใน Mockup |

---

## 6. ข้อตกลงร่วม (Design Decisions)

- **ภาษา Default:** ไทย (TH)
- **Theme Default:** Dark Mode  
- **Toggle Position:** ด้านบนขวาของหน้า, เรียงแนวนอน: `[ Light  Dark ]  [ TH  EN ]`
- **ศัพท์ทับศัพท์:** ชื่อ Technical Terms เขียนภาษาอังกฤษทุกที่ (ทั้ง TH Mode และ EN Mode)
- **Font:** ต้องรองรับภาษาไทย — แนะนำ Sarabun หรือ Noto Sans Thai จาก Google Fonts

---

## 7. ไฟล์ที่ต้องส่งกลับมา

1. **Design Mockup** (Figma / PNG) ที่อัปเดตแล้วตาม Spec ด้านบน
2. **Color Token Table** สำหรับ Light Mode
3. **Font Choice** สำหรับภาษาไทย
4. **Component Specification** (ขนาด, Padding, Border Radius) สำหรับทีม Dev ใส่ CSS

---

*เอกสารนี้จัดทำโดยทีม Dev — มิถุนายน 2569*  
*หากมีข้อสงสัยเพิ่มเติมเกี่ยวกับ Logic ด้านหลัง ติดต่อทีม Backend ได้เลย*
