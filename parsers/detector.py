import subprocess
import re


def detect_platform(pdf_path: str) -> str:
    """ตรวจแพลตฟอร์มจาก text ใน PDF"""
    result = subprocess.run(
        ["pdftotext", pdf_path, "-"],
        capture_output=True, text=True
    )
    text = result.stdout.lower()

    fb_signals = ['fbads-', 'meta platforms', 'facebook', 'ใบเสร็จสำหรับ', 'id บัญชี']
    tt_signals = ['tiktok', 'bytedance', 'tk-inv', 'tiktok for business']

    fb_score = sum(1 for s in fb_signals if s in text)
    tt_score = sum(1 for s in tt_signals if s in text)

    if fb_score > tt_score:
        return 'facebook'
    elif tt_score > 0:
        return 'tiktok'
    else:
        return 'unknown'
