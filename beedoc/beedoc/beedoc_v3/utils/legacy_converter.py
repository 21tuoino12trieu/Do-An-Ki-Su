import os
import shutil
import asyncio
import tempfile
import uuid
import logging
import platform
from typing import Optional, Dict

logger = logging.getLogger("beegen")

CONCURRENCY_LIMIT = int(os.getenv("CONVERTER_MAX_CONCURRENCY", "4"))
_converter_semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)


def _find_real_libreoffice_cmd() -> Optional[str]:
    """Find real LibreOffice binary path (excluding wrapper scripts that call MS Word)."""
    for cmd in ["libreoffice", "soffice"]:
        found = shutil.which(cmd)
        if found:
            return found
    return None


def convert_xls_to_xlsx_pure_python(xls_path: str, output_xlsx_path: str) -> str:
    """Fallback pure Python converter for .xls -> .xlsx using xlrd and openpyxl."""
    import xlrd
    import openpyxl

    xls_wb = xlrd.open_workbook(xls_path)
    xlsx_wb = openpyxl.Workbook()

    if len(xlsx_wb.sheetnames) > 0:
        default_sheet = xlsx_wb.active
        xlsx_wb.remove(default_sheet)

    for sheet_idx in range(xls_wb.nsheets):
        xls_ws = xls_wb.sheet_by_index(sheet_idx)
        raw_name = xls_ws.name or f"Sheet_{sheet_idx + 1}"
        safe_name = raw_name.replace("[", "").replace("]", "").replace("*", "").replace("?", "").replace(":", "").replace("/", "").replace("\\", "").strip()
        if not safe_name:
            safe_name = f"Sheet_{sheet_idx + 1}"

        xlsx_ws = xlsx_wb.create_sheet(title=safe_name[:30])
        for r in range(xls_ws.nrows):
            for c in range(xls_ws.ncols):
                val = xls_ws.cell_value(r, c)
                xlsx_ws.cell(row=r + 1, column=c + 1, value=val)

    xlsx_wb.save(output_xlsx_path)
    xlsx_wb.close()
    return output_xlsx_path


def _convert_with_win32com(file_path: str, output_path: str, target_ext: str) -> str:
    """Windows COM conversion using MS Office Word/Excel."""
    import win32com.client
    import pythoncom
    pythoncom.CoInitialize()
    abs_input = os.path.abspath(file_path)
    abs_output = os.path.abspath(output_path)

    if target_ext == "docx":
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = False
        try:
            doc = word.Documents.Open(abs_input, ReadOnly=True, ConfirmConversions=False)
            doc.SaveAs2(abs_output, FileFormat=16)  # 16 = wdFormatDocumentDefault (.docx)
            doc.Close(0)
        finally:
            word.Quit()
    else:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        try:
            wb = excel.Workbooks.Open(abs_input, ReadOnly=True)
            wb.SaveAs(abs_output, FileFormat=51)  # 51 = xlOpenXMLWorkbook (.xlsx)
            wb.Close(0)
        finally:
            excel.Quit()

    if not os.path.exists(abs_output):
        raise FileNotFoundError(f"COM conversion did not produce expected file: {abs_output}")

    return abs_output


async def convert_legacy_to_modern_async(file_path: str, timeout_seconds: int = 30) -> Dict[str, str]:
    """
    Asynchronously converts legacy .doc -> .docx and .xls -> .xlsx files.
    Returns dict {"modern_file_path": path} compatible with Beeflow CodeNode outputs.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source file not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower().lstrip('.')
    if ext not in ("doc", "xls"):
        return {"modern_file_path": file_path}

    target_ext = "docx" if ext == "doc" else "xlsx"
    out_dir = tempfile.gettempdir()
    base_name = os.path.splitext(os.path.basename(file_path))[0].strip()
    expected_output = os.path.join(out_dir, f"{base_name}_converted.{target_ext}")

    if os.path.exists(expected_output):
        try:
            os.remove(expected_output)
        except OSError:
            pass

    async with _converter_semaphore:
        current_os = platform.system()

        # 1. On Windows: For .xls, pure Python xlrd is fastest & most reliable
        if current_os == "Windows" and ext == "xls":
            try:
                logger.info(f"[LegacyConverter] Windows .xls converting via pure Python xlrd: {file_path}")
                res = await asyncio.to_thread(convert_xls_to_xlsx_pure_python, file_path, expected_output)
                if os.path.exists(res):
                    return {"modern_file_path": res}
            except Exception as e:
                logger.warning(f"[LegacyConverter] Pure Python .xls conversion failed ({e}), trying COM...")

        # 2. On Windows: For .doc, try win32com first
        if current_os == "Windows":
            try:
                logger.info(f"[LegacyConverter] Windows {ext} converting via win32com: {file_path}")
                res = await asyncio.to_thread(_convert_with_win32com, file_path, expected_output, target_ext)
                if os.path.exists(res):
                    return {"modern_file_path": res}
            except Exception as e:
                logger.warning(f"[LegacyConverter] Windows COM failed ({e}), trying LibreOffice...")

        # 3. Linux Production (or Windows fallback): Try LibreOffice with isolated profile
        lo_cmd = _find_real_libreoffice_cmd()
        if lo_cmd:
            profile_id = str(uuid.uuid4())
            profile_dir = os.path.join(tempfile.gettempdir(), f"lo_prof_{profile_id}")
            os.makedirs(profile_dir, exist_ok=True)
            profile_url = "file:///" + profile_dir.replace("\\", "/")

            cmd = [
                lo_cmd,
                f"-env:UserInstallation={profile_url}",
                "--headless",
                "--norestore",
                "--nolockcheck",
                "--convert-to", target_ext,
                "--outdir", out_dir,
                file_path,
            ]

            proc = None
            try:
                logger.info(f"[LegacyConverter] Converting via LibreOffice {ext} -> {target_ext}: {file_path}")
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)

                standard_lo_output = os.path.join(out_dir, f"{base_name}.{target_ext}")
                if os.path.exists(standard_lo_output):
                    if standard_lo_output != expected_output:
                        shutil.move(standard_lo_output, expected_output)
                    logger.info(f"[LegacyConverter] Successfully converted via LibreOffice: {expected_output}")
                    return {"modern_file_path": expected_output}

            except asyncio.TimeoutError:
                logger.warning(f"[LegacyConverter] LibreOffice timeout for {file_path}, killing process...")
                if proc:
                    try:
                        proc.kill()
                        await proc.wait()
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"[LegacyConverter] LibreOffice failed for {file_path}: {e}")
            finally:
                shutil.rmtree(profile_dir, ignore_errors=True)

        # 4. Final Fallback for .xls
        if ext == "xls":
            try:
                logger.info(f"[LegacyConverter] Final fallback pure Python xlrd for {file_path}")
                res = await asyncio.to_thread(convert_xls_to_xlsx_pure_python, file_path, expected_output)
                if os.path.exists(res):
                    return {"modern_file_path": res}
            except Exception as e:
                logger.error(f"[LegacyConverter] Final pure Python fallback failed for {file_path}: {e}")

        raise RuntimeError(f"Failed to convert legacy document: {file_path}")
