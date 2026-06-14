import re
import subprocess
from pathlib import Path


def extract_text_pdftotext(pdf_path: str) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", pdf_path, "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return result.stdout


def parse_tiktok_pdf(pdf_path: str) -> list[dict]:
    """Parse PDF ใบแจ้งหนี้ TikTok Ads"""
    text = extract_text_pdftotext(pdf_path)
    pages = text.split('\f')

    results = []
    for page in pages:
        if not page.strip():
            continue

        row = {}

        # Invoice number — TK-INV-XXXXXXXX หรือ รูปแบบอื่น
        m = re.search(r'(TK-INV-[\w-]+|Invoice\s*(?:No\.?|#)\s*[\w-]+)', page, re.IGNORECASE)
        row['หมายเลขใบเสร็จ'] = m.group(1).strip() if m else ''

        # วันที่
        m = re.search(r'(?:Invoice Date|Date)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})', page, re.IGNORECASE)
        row['วันที่'] = m.group(1).strip() if m else ''

        # ยอดเงิน
        m = re.search(r'(?:Total|Amount Due|Grand Total)[:\s]+(?:USD|THB|฿|\$)?\s*([\d,]+\.\d{2})', page, re.IGNORECASE)
        row['ยอดเงิน (บาท)'] = float(m.group(1).replace(',', '')) if m else 0.0

        # Advertiser
        m = re.search(r'(?:Advertiser|Bill To)[:\s]+(.+)', page, re.IGNORECASE)
        row['ชื่อเพจ'] = m.group(1).strip() if m else ''

        # Campaign
        campaigns = re.findall(r'Campaign[:\s]+(.+)', page, re.IGNORECASE)
        row['โพสต์/แคมเปญ'] = ' | '.join(c.strip() for c in campaigns) if campaigns else ''

        row['ID บัญชี'] = ''
        row['ID ธุรกรรม'] = ''
        row['แพลตฟอร์ม'] = 'TikTok'
        row['ชื่อไฟล์'] = Path(pdf_path).name
        row['สถานะ'] = 'OK' if row.get('ยอดเงิน (บาท)', 0) > 0 else 'CHECK'

        if row.get('หมายเลขใบเสร็จ') or row.get('ยอดเงิน (บาท)', 0) > 0:
            results.append(row)

    return results
