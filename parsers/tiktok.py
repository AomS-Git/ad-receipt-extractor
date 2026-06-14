import re
import subprocess
from pathlib import Path

ENGLISH_MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def extract_text_pdftotext(pdf_path: str) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", pdf_path, "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return result.stdout


def convert_english_date(raw: str) -> str:
    """แปลง '28, February, 2026' หรือ '28/02/2026' → '28/02/2026'"""
    # DD/MM/YYYY or DD-MM-YYYY
    m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', raw)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = '20' + y
        return f"{int(d):02d}/{int(mo):02d}/{y}"
    # DD, Month, YYYY or DD Month YYYY
    m = re.search(r'(\d{1,2})[,\s]+([A-Za-z]+)[,\s]+(\d{4})', raw)
    if m:
        d, month_en, y = m.group(1), m.group(2).lower(), m.group(3)
        mo = ENGLISH_MONTHS.get(month_en)
        if mo:
            return f"{int(d):02d}/{mo:02d}/{y}"
    # YYYY-MM-DD
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', raw)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return raw.strip()


def parse_tiktok_pdf(pdf_path: str) -> list[dict]:
    """Parse PDF ใบแจ้งหนี้ TikTok Ads — รองรับรูปแบบ THTT/TK-INV"""
    text = extract_text_pdftotext(pdf_path)
    pages = text.split('\f')

    results = []
    for page in pages:
        if not page.strip():
            continue

        # ต้องมี marker ของ TikTok
        if not any(k in page for k in ['TIKTOK', 'TikTok', 'Invoice No', 'TAX INVOICE', 'TK-INV']):
            continue

        row = {}

        # Invoice number — THTT... หรือ TK-INV-...
        m = re.search(r'Invoice\s*No\.?\s*[:\s]*([\w-]+)', page, re.IGNORECASE)
        if m:
            row['หมายเลขใบเสร็จ'] = m.group(1).strip()
        else:
            m = re.search(r'(TK-INV-[\w-]+)', page, re.IGNORECASE)
            row['หมายเลขใบเสร็จ'] = m.group(1).strip() if m else ''

        # วันที่
        m = re.search(r'Invoice\s*Date[:\s]+(.+)', page, re.IGNORECASE)
        row['วันที่'] = convert_english_date(m.group(1)) if m else ''

        # ยอดเงิน — Total Amount Due หรือ Grand Total
        m = re.search(r'Total\s*Amount\s*Due\s+([\d,]+\.\d{2})', page, re.IGNORECASE)
        if not m:
            m = re.search(r'(?:Grand\s*Total|Amount\s*Due)[:\s]+(?:USD|THB|฿|\$)?\s*([\d,]+\.\d{2})', page, re.IGNORECASE)
        row['ยอดเงิน (บาท)'] = float(m.group(1).replace(',', '')) if m else 0.0

        # ชื่อ Client — "Client Name" label
        m = re.search(r'Client\s*Name\s+(.+)', page, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            # กรณีชื่อยาวข้ามบรรทัด (มี Billing Address ตาม)
            name = re.split(r'(?:Billing|Invoice|Due|Contract|Tax\s*#)', name)[0].strip()
            row['ชื่อเพจ'] = name
        else:
            m = re.search(r'(?:Advertiser|Bill\s*To)[:\s]+(.+)', page, re.IGNORECASE)
            row['ชื่อเพจ'] = m.group(1).strip() if m else ''

        # Contract No
        m = re.search(r'Contract\s*No\.?\s*([\w-]+)', page, re.IGNORECASE)
        row['ID ธุรกรรม'] = m.group(1).strip() if m else ''

        row['ID บัญชี'] = ''
        row['โพสต์/แคมเปญ'] = ''
        row['แพลตฟอร์ม'] = 'TikTok'
        row['ชื่อไฟล์'] = Path(pdf_path).name
        row['สถานะ'] = 'OK' if row.get('ยอดเงิน (บาท)', 0) > 0 else 'CHECK'

        if row.get('หมายเลขใบเสร็จ') or row.get('ยอดเงิน (บาท)', 0) > 0:
            results.append(row)

    return results
