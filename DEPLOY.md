# 📖 วิธี Deploy Web App — Step by Step

## ✅ ทีมไม่ต้องติดตั้งอะไรเลย
เพียงเปิดเว็บ → วาง PDF → กด Download

---

## 🚀 Deploy ขึ้น Railway (แนะนำ — ฟรีทดลอง)

### ขั้นตอนที่ 1 — สมัคร Railway
1. ไปที่ https://railway.app
2. กด **"Login with GitHub"**
3. สมัครฟรี (มี $5 credit ทดลองใช้)

### ขั้นตอนที่ 2 — สร้าง GitHub Repo
1. ไปที่ https://github.com/new
2. ตั้งชื่อ repo: `ad-receipt-extractor`
3. กด **"Create repository"**
4. อัปโหลดทุกไฟล์จาก folder `webapp/` ขึ้น repo

### ขั้นตอนที่ 3 — Deploy บน Railway
1. ไปที่ https://railway.app/new
2. กด **"Deploy from GitHub repo"**
3. เลือก repo `ad-receipt-extractor`
4. Railway จะ build อัตโนมัติ (~3 นาที)
5. กด **"Generate Domain"** → ได้ URL เช่น `https://ad-receipt-xxx.up.railway.app`

### ขั้นตอนที่ 4 — แชร์ URL ให้ทีม
ส่ง URL ให้ทีม → เปิดเว็บ → ใช้งานได้เลย ✅

---

## 💻 รันบนเครื่องตัวเอง (ทดสอบก่อน Deploy)

### macOS / Linux
```bash
# ติดตั้ง poppler (ครั้งเดียว)
brew install poppler          # macOS
sudo apt install poppler-utils # Ubuntu/Linux

# ติดตั้ง Python packages
pip3 install -r requirements.txt

# รัน server
python3 -m uvicorn server:app --reload --port 8000

# เปิดเว็บ
open http://localhost:8000
```

### Windows
```bash
# ติดตั้ง Scoop ก่อน (package manager)
# เปิด PowerShell แล้วรัน:
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# ติดตั้ง poppler
scoop install poppler

# ติดตั้ง Python packages
pip install -r requirements.txt

# รัน server
uvicorn server:app --reload --port 8000

# เปิดเว็บ
start http://localhost:8000
```

### Docker (ทุก OS — ง่ายสุด)
```bash
# ต้องติดตั้ง Docker Desktop ก่อน
docker build -t receipt-app .
docker run -p 8000:8000 receipt-app

# เปิดเว็บ
open http://localhost:8000
```

---

## 💰 ค่าใช้จ่าย Railway

| Plan | ราคา | เหมาะกับ |
|------|------|----------|
| Hobby (ฟรี) | $0 | ทดลอง / ทีมเล็ก |
| Starter | $5/เดือน | ทีม 3–10 คน |
| Pro | $20/เดือน | ทีมใหญ่ / ใช้หนัก |

---

## 🔒 ถ้าต้องการ Login / Password

เพิ่ม environment variable บน Railway:
```
APP_PASSWORD=รหัสผ่านที่ต้องการ
```

แล้วระบบจะถามรหัสก่อนเข้าใช้งาน (แจ้งได้ถ้าต้องการ feature นี้)

---

## 📞 ปัญหาที่พบบ่อย

| ปัญหา | วิธีแก้ |
|-------|---------|
| Build ไม่ผ่าน | ตรวจว่า Dockerfile อยู่ใน root folder |
| PDF อ่านไม่ได้ | ตรวจว่าไฟล์ไม่ได้ password-protected |
| Server หยุดเอง | Railway Hobby จะหยุดถ้าไม่ใช้ 30 นาที (upgrade เป็น Starter) |
