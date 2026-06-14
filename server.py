import os, sys, uuid, tempfile, secrets
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent))
from parsers.detector import detect_platform
from parsers.facebook import parse_facebook_pdf
from parsers.tiktok import parse_tiktok_pdf
from excel_writer import create_excel
from excel_merger import merge_excels, read_excel_rows

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Password ──────────────────────────────────────────────────
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SESSIONS: set[str] = set()

def _is_authed(request: Request) -> bool:
    if not APP_PASSWORD:
        return True
    return request.cookies.get("auth_token", "") in SESSIONS

@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    if not APP_PASSWORD or body.get("password") == APP_PASSWORD:
        token = secrets.token_hex(32)
        SESSIONS.add(token)
        resp = JSONResponse({"ok": True})
        resp.set_cookie("auth_token", token, httponly=True, samesite="lax", max_age=86400 * 7)
        return resp
    return JSONResponse({"ok": False, "error": "รหัสผ่านไม่ถูกต้อง"}, status_code=401)

@app.post("/api/logout")
async def logout(request: Request, response: Response):
    SESSIONS.discard(request.cookies.get("auth_token", ""))
    response.delete_cookie("auth_token")
    return JSONResponse({"ok": True})

@app.get("/api/auth-check")
async def auth_check(request: Request):
    return JSONResponse({"authed": _is_authed(request), "has_password": bool(APP_PASSWORD)})

# ── Upload / Process PDF ──────────────────────────────────────
UPLOAD_DIR = Path(tempfile.gettempdir()) / "receipts"
UPLOAD_DIR.mkdir(exist_ok=True)

@app.post("/api/process")
async def process_pdfs(request: Request, files: list[UploadFile] = File(...)):
    if not _is_authed(request):
        return JSONResponse({"error": "กรุณา login ก่อน"}, status_code=401)

    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir()

    rows_fb, rows_tt, rows_err, results_meta = [], [], [], []

    for f in files:
        tmp_path = session_dir / f.filename
        tmp_path.write_bytes(await f.read())
        try:
            platform = detect_platform(str(tmp_path))
            if platform == "facebook":
                rows = parse_facebook_pdf(str(tmp_path))
            elif platform == "tiktok":
                rows = parse_tiktok_pdf(str(tmp_path))
            else:
                rows = [{"ชื่อไฟล์": f.filename, "สถานะ": "CHECK",
                         "หมายเหตุ": "ตรวจไม่ออก", "แพลตฟอร์ม": "unknown"}]

            ok_count = err_count = 0
            for row in rows:
                status = row.get("สถานะ", "OK")
                if status in ("OCR_NEEDED", "CHECK", "ERROR") or row.get("แพลตฟอร์ม") == "unknown":
                    rows_err.append(row); err_count += 1
                elif platform == "facebook":
                    rows_fb.append(row); ok_count += 1
                else:
                    rows_tt.append(row); ok_count += 1

            results_meta.append({
                "filename": f.filename, "platform": platform,
                "ok": ok_count, "err": err_count,
                "status": "error" if err_count > 0 and ok_count == 0 else ("warn" if err_count > 0 else "ok"),
                "rows": [r for r in rows if r.get("สถานะ") == "OK"],
            })
        except Exception as e:
            results_meta.append({"filename": f.filename, "platform": "unknown",
                                  "ok": 0, "err": 1, "status": "error", "rows": [], "error": str(e)})

    out_path = session_dir / "ใบเสร็จโฆษณา.xlsx"
    create_excel(rows_fb, rows_tt, rows_err, str(out_path))

    return JSONResponse({
        "session_id": session_id,
        "total_files": len(files),
        "total_ok": len(rows_fb) + len(rows_tt),
        "total_err": len(rows_err),
        "files": results_meta,
        "rows": rows_fb + rows_tt,
        "download_url": f"/api/download/{session_id}",
    })

@app.get("/api/download/{session_id}")
def download(session_id: str, request: Request):
    if not _is_authed(request):
        return JSONResponse({"error": "กรุณา login ก่อน"}, status_code=401)
    path = UPLOAD_DIR / session_id / "ใบเสร็จโฆษณา.xlsx"
    if not path.exists():
        return JSONResponse({"error": "ไม่พบไฟล์"}, status_code=404)
    return FileResponse(str(path), filename="ใบเสร็จโฆษณา.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── Merge Excel ───────────────────────────────────────────────
@app.post("/api/merge")
async def merge_excel_files(request: Request, files: list[UploadFile] = File(...)):
    """รับ Excel หลายไฟล์ (จากหลายเพจ) → merge เป็นไฟล์เดียว"""
    if not _is_authed(request):
        return JSONResponse({"error": "กรุณา login ก่อน"}, status_code=401)

    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir()

    saved_paths = []
    file_summaries = []
    total_rows = 0

    for f in files:
        if not f.filename.lower().endswith('.xlsx'):
            file_summaries.append({"filename": f.filename, "status": "skip", "rows": 0})
            continue
        tmp_path = session_dir / f.filename
        tmp_path.write_bytes(await f.read())
        try:
            rows = read_excel_rows(str(tmp_path))
            saved_paths.append(str(tmp_path))
            total_rows += len(rows)
            file_summaries.append({"filename": f.filename, "status": "ok", "rows": len(rows)})
        except Exception as e:
            file_summaries.append({"filename": f.filename, "status": "error", "rows": 0, "error": str(e)})

    # merge
    wb = merge_excels(saved_paths)
    out_path = session_dir / "รวมใบเสร็จทุกเพจ.xlsx"
    wb.save(str(out_path))

    return JSONResponse({
        "session_id": session_id,
        "total_files": len(saved_paths),
        "total_rows": total_rows,
        "files": file_summaries,
        "download_url": f"/api/download-merge/{session_id}",
    })

@app.get("/api/download-merge/{session_id}")
def download_merge(session_id: str, request: Request):
    if not _is_authed(request):
        return JSONResponse({"error": "กรุณา login ก่อน"}, status_code=401)
    path = UPLOAD_DIR / session_id / "รวมใบเสร็จทุกเพจ.xlsx"
    if not path.exists():
        return JSONResponse({"error": "ไม่พบไฟล์"}, status_code=404)
    return FileResponse(str(path), filename="รวมใบเสร็จทุกเพจ.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.get("/api/merge-preview/{session_id}")
def merge_preview(session_id: str, request: Request):
    """ส่งข้อมูล preview สำหรับแสดงผลใน UI"""
    if not _is_authed(request):
        return JSONResponse({"error": "กรุณา login ก่อน"}, status_code=401)
    path = UPLOAD_DIR / session_id / "รวมใบเสร็จทุกเพจ.xlsx"
    if not path.exists():
        return JSONResponse({"error": "ไม่พบไฟล์"}, status_code=404)

    from excel_merger import read_excel_rows
    from collections import defaultdict

    # อ่าน rows จากไฟล์ที่รวมแล้ว — sheet รายบิลทั้งหมด
    wb = __import__('openpyxl').load_workbook(str(path), data_only=True)
    bills, daily_map = [], defaultdict(lambda: {'count':0,'total':0.0})

    if 'รายบิลทั้งหมด' in wb.sheetnames:
        ws = wb['รายบิลทั้งหมด']
        headers = [ws.cell(1,c).value for c in range(1, ws.max_column+1)]
        for r in range(2, ws.max_row+1):
            row = {h: ws.cell(r,c).value for c,h in enumerate(headers,1) if h}
            if not row.get('วันที่'): continue
            amt = row.get('ยอดเงิน (บาท)', 0) or 0
            try: amt = float(amt)
            except: amt = 0.0
            bills.append({'date': str(row.get('วันที่','')), 'amount': amt,
                           'page': str(row.get('ชื่อเพจ',''))})
            d = str(row.get('วันที่',''))
            if d:
                daily_map[d]['count'] += 1
                daily_map[d]['total'] += amt

    daily = sorted(
        [{'date':k,'count':v['count'],'total':round(v['total'],2)} for k,v in daily_map.items()],
        key=lambda x: tuple(int(p) for p in reversed(x['date'].split('/'))) if '/' in x['date'] else (0,0,0)
    )
    grand = sum(d['total'] for d in daily)
    daily.append({'date':'รวมทั้งหมด','count':sum(d['count'] for d in daily[:-1] if d['date']!='รวมทั้งหมด'),'total':round(grand,2)})

    return JSONResponse({"bills": bills, "daily": daily})
