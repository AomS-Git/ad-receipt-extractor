import re
import subprocess
import tempfile
import os
from pathlib import Path
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

THAI_MONTHS = {
    'ม.ค.': 1, 'มกราคม': 1,
    'ก.พ.': 2, 'กุมภาพันธ์': 2,
    'มี.ค.': 3, 'มีนาคม': 3,
    'เม.ย.': 4, 'เมษายน': 4,
    'พ.ค.': 5, 'พฤษภาคม': 5,
    'มิ.ย.': 6, 'มิถุนายน': 6,
    'ก.ค.': 7, 'กรกฎาคม': 7,
    'ส.ค.': 8, 'สิงหาคม': 8,
    'ก.ย.': 9, 'กันยายน': 9,
    'ต.ค.': 10, 'ตุลาคม': 10,
    'พ.ย.': 11, 'พฤศจิกายน': 11,
    'ธ.ค.': 12, 'ธันวาคม': 12,
}

def convert_thai_date(raw: str) -> str:
    """แปลง '18 พ.ค. 2026 06:28' → '18/05/2026'"""
    if not raw:
        return ''
    # ดึง วัน เดือน ปี
    m = re.search(r'(\d{1,2})\s+([\u0E00-\u0E7F\.]+)\s+(\d{4})', raw)
    if not m:
        return raw
    day, month_th, year = m.group(1), m.group(2), m.group(3)
    month_num = THAI_MONTHS.get(month_th.strip())
    if not month_num:
        return raw
    return f"{int(day):02d}/{month_num:02d}/{year}"


def extract_text_pdfplumber(pdf_path: str) -> str:
    """ใช้ pdfplumber (Unicode-safe) แยกหน้าด้วย \f"""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or '')
    return '\f'.join(pages)


def extract_text_pdftotext(pdf_path: str) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", pdf_path, "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return result.stdout


def extract_text(pdf_path: str) -> str:
    """ใช้ pdfplumber ก่อน ถ้าไม่มีค่อย fallback pdftotext"""
    if HAS_PDFPLUMBER:
        try:
            text = extract_text_pdfplumber(pdf_path)
            if text.strip():
                return text
        except Exception:
            pass
    return extract_text_pdftotext(pdf_path)


def is_garbled(page_text: str) -> bool:
    """ตรวจว่าหน้านี้ OCR อ่านไม่ออก"""
    if len(page_text.strip()) < 50:
        return False
    has_thai = bool(re.search(r'[\u0E00-\u0E7F]', page_text))
    has_key = any(k in page_text for k in ['ใบเสร็จสำหรับ', 'FBADS-', 'ID บัญชี', 'ชำระแล้ว', 'ชำระแลว'])
    return not (has_thai and has_key)


def parse_page(page_text: str) -> dict | None:
    """Parse 1 หน้าใบเสร็จ Facebook → dict หรือ None ถ้าไม่ใช่ใบเสร็จ"""

    # ข้ามหน้า continuation
    if re.search(r'\d\s*จาก\s*\d', page_text[:150]):
        first_receipt = re.search(r'ใบเสร็จสำหรับ', page_text)
        if not first_receipt:
            return None

    # ต้องมี marker หลัก
    if 'ใบเสร็จสำหรับ' not in page_text and 'FBADS-' not in page_text:
        return None

    row = {}

    # ชื่อเพจ
    m = re.search(r'ใบเสร็จสำหรับ\s+(.+)', page_text)
    row['ชื่อเพจ'] = m.group(1).strip() if m else ''

    # ID บัญชี
    m = re.search(r'ID\s*บัญชี[:\s]+(\d+)', page_text)
    row['ID บัญชี'] = m.group(1).strip() if m else ''

    # วันที่
    m = re.search(r'วันที่เรียกเก็บเงิน/ชำระเงิน\s*\n\s*(.+)', page_text)
    raw_date = m.group(1).strip() if m else ''
    row['วันที่'] = convert_thai_date(raw_date)

    # ID ธุรกรรม
    m = re.search(r'ID\s*ธุรกรรม\s*\n\s*(\S+)', page_text)
    row['ID ธุรกรรม'] = m.group(1).strip() if m else ''

    # ยอดเงิน — หา ฿XXX.XX ที่อยู่ใกล้กับ "ชำระแล้ว" หรือ "ชำระแลว"
    amounts = re.findall(r'฿([\d,]+\.\d{2})', page_text)
    if amounts:
        # ยอดหลักคือยอดที่ใหญ่ที่สุด (หรือยอดแรกที่ใกล้ "ชำระ")
        m_paid = re.search(r'(?:ชำระแล้ว|ชำระแลว).*?฿([\d,]+\.\d{2})', page_text, re.DOTALL)
        if m_paid:
            row['ยอดเงิน (บาท)'] = float(m_paid.group(1).replace(',', ''))
        else:
            nums = [float(a.replace(',', '')) for a in amounts]
            row['ยอดเงิน (บาท)'] = max(nums)
    else:
        row['ยอดเงิน (บาท)'] = 0.0

    # หมายเลขใบเสร็จ (FBADS-xxx หรือ ID ธุรกรรมแทน สำหรับใบ top-up)
    m = re.search(r'(FBADS-[\d]+-[\d]+)', page_text)
    if m:
        row['หมายเลขใบเสร็จ'] = m.group(1).strip()
    else:
        # ใบ top-up ไม่มี FBADS — ใช้ ID ธุรกรรมแทน
        row['หมายเลขใบเสร็จ'] = row.get('ID ธุรกรรม', '')

    # โพสต์/แคมเปญ — บรรทัดที่มี "โพสต์:" หรือ "โพสต:" แต่ไม่มี "อิมเพรสชัน"
    posts = re.findall(r'โพสต[์:]?\s*[":]\s*"?(.+?)"?\s*(?:\n|$)', page_text)
    posts_clean = [p.strip().strip('"') for p in posts if 'อิมเพรสชัน' not in p and p.strip()]
    row['โพสต์/แคมเปญ'] = ' | '.join(posts_clean) if posts_clean else ''

    # platform
    row['แพลตฟอร์ม'] = 'Facebook'

    return row


def parse_facebook_pdf(pdf_path: str) -> list[dict]:
    """Parse PDF ใบเสร็จ FB — รองรับหลายหน้า / หลายใบเสร็จใน 1 ไฟล์"""
    text = extract_text(pdf_path)
    pages = text.split('\f')

    results = []
    for page in pages:
        if not page.strip():
            continue
        if is_garbled(page):
            # TODO: fallback OCR / Google Doc AI
            results.append({
                'แพลตฟอร์ม': 'Facebook',
                'ชื่อไฟล์': Path(pdf_path).name,
                'สถานะ': 'OCR_NEEDED',
                'หมายเหตุ': 'pdftotext อ่านไม่ได้ ต้องใช้ OCR'
            })
            continue

        row = parse_page(page)
        if row:
            row['ชื่อไฟล์'] = Path(pdf_path).name
            row['สถานะ'] = 'OK' if row.get('ยอดเงิน (บาท)', 0) > 0 else 'CHECK'
            results.append(row)

    return results
