import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import fitz
import pyotp
import requests


SCROLL_PDF_EXPORTS_PATH = "/plugins/servlet/scroll-pdf/api/exports"
DEFAULT_TEMPLATE_ID = "com.k15t.scroll.pdf.default-template-documentation"
OTP_FORM_MARKER = 'id="otp-validate-form"'
LOGIN_FORM_MARKER = 'action="/dologin.action"'


def normalize_file_name(value: str) -> str:
    normalized = re.sub(r"[^\w.-]+", "_", str(value or "").strip(), flags=re.UNICODE).strip("._")
    return normalized or "confluence_page"


def resolve_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", str(path or "").lstrip("/"))


def is_pdf(content: bytes) -> bool:
    return content.lstrip().startswith(b"%PDF")


def browser_user_agent() -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"
    )


def is_html_response(response: requests.Response) -> bool:
    return "html" in (response.headers.get("Content-Type") or "").lower()


def is_otp_response(response: requests.Response) -> bool:
    return is_html_response(response) and OTP_FORM_MARKER in response.text


def is_login_response(response: requests.Response) -> bool:
    return is_html_response(response) and LOGIN_FORM_MARKER in response.text


def login(session: requests.Session, base_url: str, username: str, password: str, otp_secret: str, destination: str) -> None:
    response = session.post(
        resolve_url(base_url, "/dologin.action"),
        data={
            "os_username": username,
            "os_password": password,
            "os_cookie": "true",
            "os_destination": destination,
            "login": "Log in",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=True,
        timeout=30,
    )
    response.raise_for_status()
    if is_login_response(response):
        raise RuntimeError("Confluence web login failed.")
    if not is_otp_response(response):
        return

    otp_response = session.post(
        response.url,
        data={"validate_otp": pyotp.TOTP(otp_secret).now(), "Validate": "Xác nhận mã"},
        headers={"Referer": response.url, "Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=True,
        timeout=30,
    )
    otp_response.raise_for_status()
    if is_otp_response(otp_response):
        raise RuntimeError("Confluence rejected the generated TOTP code.")


def output_path(output_pdf: str, output_dir: str, page_title: str, page_id: str) -> Path:
    file_name = f"{normalize_file_name(page_title or page_id)}.pdf"
    if not output_pdf:
        return (Path(output_dir or "assets") / file_name).resolve()

    target = Path(output_pdf).resolve()
    if target.exists() and target.is_dir():
        return target / file_name
    if target.suffix.lower() != ".pdf":
        return target / file_name
    return target


def scroll_pdf_headers(base_url: str, page_id: str) -> dict[str, str]:
    return {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": base_url.rstrip("/"),
        "Referer": resolve_url(base_url, f"/pages/viewpage.action?pageId={page_id}"),
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": browser_user_agent(),
    }


def scroll_pdf_payload(page_id: str) -> dict[str, Any]:
    return {
        "pageId": str(page_id),
        "pageSet": "current",
        "templateId": DEFAULT_TEMPLATE_ID,
        "properties": {
            "labels": {
                "includeContentWithLabels": [],
                "excludeContentWithLabels": [],
                "indexTerms": [],
            },
            "content": {
                "headings": "enableNumberedHeadings",
                "layout": [],
                "links": ["enableExternalLinks", "enableConfluenceLinks"],
                "tables": "repeatTableHeaders",
                "pagebreak": [],
                "comalaWorkflows": [],
                "attachments": "notEmbedAttachments",
            },
            "macros": {"macros": ["showTocOutput", "showChildrenOutput"]},
            "title": {"figure": "after", "table": "after"},
            "printOptions": {
                "artifactFileName": "${document.title}-v${document.rootPage.revision}-${export.date(\"YYYMMdd_HHmmss\")}",
                "optimization": "optimizePrint",
                "documentLinkSuffix": " (see page ${target-page})",
                "figureLinkSuffix": " (see figure ${target-number})",
                "tableLinkSuffix": " (see table ${target-number})",
                "pdfCompliance": [],
                "imageCompression": "none",
            },
            "metadata": {"title": "", "author": "", "subject": "", "keywords": ""},
            "locale": {"defaultLocale": "en"},
            "bookmarks": {"level": "3", "expandedLevel": "3", "bookmarksPanel": []},
        },
        "pageOptions": {},
        "locale": "en-US",
        "debugMode": False,
        "initiator": "EXPORT_DIALOG",
    }


def require_json(response, context: str) -> dict[str, Any]:
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"{context} did not return JSON: {response.text[:500]!r}") from exc


def export_status_name(status: dict[str, Any]) -> str:
    return str(status.get("name") or status.get("status") or status.get("state") or "").lower()


def start_export(session: requests.Session, base_url: str, page_id: str) -> str:
    response = session.post(
        resolve_url(base_url, SCROLL_PDF_EXPORTS_PATH),
        headers=scroll_pdf_headers(base_url, page_id),
        data=json.dumps(scroll_pdf_payload(page_id), ensure_ascii=False),
        allow_redirects=True,
        timeout=75,
    )
    data = require_json(response, "Scroll PDF create export")
    export_id = str(data.get("exportJobId") or data.get("jobId") or data.get("id") or "").strip()
    if not export_id:
        raise RuntimeError(f"Scroll PDF create export response has no export id: {data!r}")
    return export_id


def wait_for_export(
    session: requests.Session,
    base_url: str,
    page_id: str,
    export_id: str,
    timeout_seconds: int,
    poll_interval: float,
) -> dict[str, Any]:
    status_url = resolve_url(base_url, f"{SCROLL_PDF_EXPORTS_PATH}/{export_id}/status")
    deadline = time.monotonic() + timeout_seconds
    last_status: dict[str, Any] = {}

    while time.monotonic() < deadline:
        response = session.get(
            status_url,
            headers=scroll_pdf_headers(base_url, page_id),
            allow_redirects=True,
            timeout=30,
        )
        last_status = require_json(response, "Scroll PDF export status")
        name = export_status_name(last_status)
        print(f"scroll_pdf_status: {name or last_status}")

        if last_status.get("downloadUrl"):
            return last_status
        if name in {"complete", "completed", "done", "finished", "success", "successful"}:
            return last_status
        if name in {"failed", "failure", "error", "errored", "cancelled", "canceled"}:
            raise RuntimeError(f"Scroll PDF export failed: {last_status!r}")

        time.sleep(max(0.1, poll_interval))

    raise TimeoutError(f"Timed out waiting for Scroll PDF export {export_id}: {last_status!r}")


def download_artifact(
    session: requests.Session,
    base_url: str,
    page_id: str,
    export_id: str,
    status: dict[str, Any],
) -> bytes:
    download_url = str(status.get("downloadUrl") or "").strip()
    if not download_url:
        raise RuntimeError(f"Scroll PDF status has no downloadUrl: {status!r}")

    response = session.get(
        urljoin(base_url.rstrip("/") + "/", download_url),
        headers={
            "Accept": "application/pdf,*/*",
            "Referer": resolve_url(base_url, f"/pages/viewpage.action?pageId={page_id}"),
            "User-Agent": browser_user_agent(),
        },
        allow_redirects=True,
        timeout=75,
    )
    response.raise_for_status()
    if not is_pdf(response.content):
        raise RuntimeError(f"Downloaded artifact is not a PDF for export {export_id}.")
    return response.content


def remove_template_pages(
    pdf_content: bytes,
    *,
    keep_cover: bool,
    keep_toc: bool,
) -> bytes:
    doc = fitz.open(stream=pdf_content, filetype="pdf")
    try:
        removed = False
        if not keep_cover and doc.page_count:
            doc.delete_page(0)
            removed = True

        if not keep_toc:
            for page_index in range(min(4, doc.page_count)):
                text = doc.load_page(page_index).get_text("text")
                if "Table of Contents" in text:
                    doc.delete_page(page_index)
                    removed = True
                    break

        if not removed:
            return pdf_content
        return doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()


def export_scroll_pdf(
    session: requests.Session,
    base_url: str,
    page_id: str,
    username: str,
    password: str,
    otp_secret: str,
    poll_timeout: int,
    poll_interval: float,
) -> bytes:
    login(session, base_url, username, password, otp_secret, f"/pages/viewpage.action?pageId={page_id}")
    export_id = start_export(session, base_url, page_id)
    print(f"scroll_pdf_export_id: {export_id}")
    status = wait_for_export(session, base_url, page_id, export_id, poll_timeout, poll_interval)
    return download_artifact(session, base_url, page_id, export_id, status)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a Confluence page to PDF through Scroll PDF.")
    parser.add_argument("--url", default=os.getenv("CONFLUENCE_URL", "https://confluence.mbbank.com.vn"))
    parser.add_argument("--page-id", default=os.getenv("CONFLUENCE_PAGE_ID", "855250712"))
    parser.add_argument("--page-title", default=os.getenv("CONFLUENCE_PAGE_TITLE", ""))
    parser.add_argument("--username", default=os.getenv("CONFLUENCE_USERNAME", "aiplatform"))
    parser.add_argument("--password", default=os.getenv("CONFLUENCE_PASSWORD", "Rndai@2026!!"))
    parser.add_argument("--otp-secret", default=os.getenv("CONFLUENCE_OTP_SECRET", "REPLACE_WITH_LOCAL_SECRET"))
    parser.add_argument("--output-dir", default=os.getenv("CONFLUENCE_OUTPUT_DIR", "assets"))
    parser.add_argument("--output-pdf", default=os.getenv("CONFLUENCE_OUTPUT_PDF", ""))
    parser.add_argument("--poll-timeout", type=int, default=int(os.getenv("CONFLUENCE_EXPORT_POLL_TIMEOUT", "180")))
    parser.add_argument("--poll-interval", type=float, default=float(os.getenv("CONFLUENCE_EXPORT_POLL_INTERVAL", "2")))
    parser.add_argument("--keep-cover", action="store_true", help="Keep Scroll PDF cover page.")
    parser.add_argument("--keep-toc", action="store_true", help="Keep Scroll PDF Table of Contents page.")
    return parser


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    args = build_parser().parse_args()
    session = requests.Session()
    page_title = str(args.page_title or args.page_id).strip()
    pdf_content = export_scroll_pdf(
        session,
        args.url,
        args.page_id,
        args.username,
        args.password,
        args.otp_secret,
        poll_timeout=args.poll_timeout,
        poll_interval=args.poll_interval,
    )
    pdf_content = remove_template_pages(
        pdf_content,
        keep_cover=args.keep_cover,
        keep_toc=args.keep_toc,
    )

    target = output_path(args.output_pdf, args.output_dir, page_title, args.page_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(pdf_content)

    print(f"page_id: {args.page_id}")
    print(f"page_title: {page_title}")
    print(f"output_pdf: {target}")
    print(f"file_size_bytes: {target.stat().st_size}")


if __name__ == "__main__":
    main()
