import os
import platform
import shutil
import subprocess
import tempfile
from typing import Optional

import logging

logger = logging.getLogger("beegen")


def _convert_with_docx2pdf(docx_path: str, pdf_path: str) -> None:
    """Convert DOCX to PDF using docx2pdf (requires Microsoft Word on Windows)."""
    from docx2pdf import convert
    convert(docx_path, pdf_path)


def _convert_with_libreoffice(docx_path: str, output_dir: str) -> str:
    """Convert DOCX to PDF using LibreOffice headless (Linux/Docker)."""
    if shutil.which("libreoffice") is None:
        raise EnvironmentError(
            "LibreOffice is not installed or not found on PATH. "
            "It is required for DOCX-to-PDF conversion on Linux.\n"
            "To install in Docker, add to your Dockerfile:\n"
            "  RUN apt-get update && apt-get install -y libreoffice-writer && rm -rf /var/lib/apt/lists/*\n"
            "For Ubuntu/Debian host:\n"
            "  sudo apt-get install libreoffice-writer"
        )
    result = subprocess.run(
        [
            "libreoffice", "--headless", "--norestore",
            "--convert-to", "pdf",
            "--outdir", output_dir,
            docx_path,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"LibreOffice conversion failed (exit {result.returncode}): {result.stderr}"
        )

    base_name = os.path.splitext(os.path.basename(docx_path))[0]
    pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(
            f"LibreOffice did not produce expected PDF: {pdf_path}. "
            f"stdout: {result.stdout}, stderr: {result.stderr}"
        )
    return pdf_path


def convert_docx_to_pdf(docx_path: str, output_dir: Optional[str] = None) -> dict:
    """
    Converts a DOCX file to PDF.

    Platform handling:
      - **Windows**: Uses ``docx2pdf`` (requires Microsoft Word).
      - **Linux / other**: Uses LibreOffice in headless mode
        (``libreoffice`` must be available on PATH).
    """
    if not os.path.exists(docx_path):
        raise FileNotFoundError(f"DOCX file not found: {docx_path}")

    if output_dir is None:
        output_dir = tempfile.gettempdir()

    base_name = os.path.splitext(os.path.basename(docx_path))[0]
    pdf_path = os.path.join(output_dir, f"{base_name}.pdf")

    current_os = platform.system()
    logger.info(f"Converting DOCX to PDF on {current_os}: {docx_path}")

    if current_os == "Windows":
        _convert_with_docx2pdf(docx_path, pdf_path)
    else:
        # Linux, Darwin, or any non-Windows OS → use LibreOffice headless
        pdf_path = _convert_with_libreoffice(docx_path, output_dir)

    logger.info(f"PDF created: {pdf_path}")
    return {"pdf_path": pdf_path}
