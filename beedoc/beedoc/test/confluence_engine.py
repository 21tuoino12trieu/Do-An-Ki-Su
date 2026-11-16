import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ensure the package is in the search path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Beedoc Confluence HTML pipeline against a page_id.",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("CONFLUENCE_URL", "https://confluence.mbbank.com.vn"),
        help="Confluence base URL. Defaults to CONFLUENCE_URL.",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("CONFLUENCE_TOKEN", ""),
        help="Confluence token. Defaults to CONFLUENCE_TOKEN.",
    )
    parser.add_argument(
        "--page-id",
        default=os.getenv("CONFLUENCE_PAGE_ID", "247886912"),
        help="Confluence page ID. Defaults to CONFLUENCE_PAGE_ID.",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("CONFLUENCE_USERNAME", ""),
        help="Confluence web username used when attachments require web login.",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("CONFLUENCE_PASSWORD", ""),
        help="Confluence web password used when attachments require web login.",
    )
    parser.add_argument(
        "--otp-secret",
        default=os.getenv("CONFLUENCE_OTP_SECRET", ""),
        help="TOTP secret used when attachments require Mobile Authenticator.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=10000,
        help="How many characters of reconstructed_content to print.",
    )
    parser.add_argument(
        "--output-txt",
        default="assets/output_markdown.txt",
        help="Optional path to save reconstructed_content as a UTF-8 text file.",
    )
    return parser


async def run(
    url: str,
    token: str,
    page_id: str,
    username: str,
    password: str,
    otp_secret: str,
    preview_chars: int,
    output_txt: str,
) -> None:
    if not url or not token or not page_id:
        raise ValueError("Missing required values. Provide --url, --token, --page-id or matching env vars.")

    from beedoc_v3.engine import BeedocEngine

    engine = BeedocEngine(
        config={
            "url": url,
            "token": token,
            "username": username,
            "password": password,
            "otp_secret": otp_secret,
        }
    )
    document = await engine.process_confluence(page_id=page_id)
    output_path = Path(output_txt).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    reconstructed_content = document.reconstructed_content or ""
    if reconstructed_content.strip():
        output_text = reconstructed_content
    else:
        output_text = "\n".join(
            [
                f"status: {document.status}",
                f"page_id: {document.source_metadata.get('page_id')}",
                f"page_title: {document.source_metadata.get('page_title')}",
                f"file_name: {document.file_name}",
                f"file_path: {document.file_path}",
                f"file_hash: {document.file_hash}",
                f"file_size_bytes: {document.file_size_bytes}",
                f"error_message: {document.error_message}",
                f"reconstructed_content_length: {len(reconstructed_content)}",
                "",
                "reconstructed_content is empty.",
            ]
        )
    output_path.write_text(output_text, encoding="utf-8")

    print(f"status: {document.status}")
    print(f"page_id: {document.source_metadata.get('page_id')}")
    print(f"page_title: {document.source_metadata.get('page_title')}")
    print(f"file_name: {document.file_name}")
    print(f"file_path: {document.file_path}")
    print(f"file_hash: {document.file_hash}")
    print(f"file_size_bytes: {document.file_size_bytes}")
    print(f"error_message: {document.error_message}")
    print(f"output_txt: {output_path}")
    print(f"reconstructed_content_length: {len(reconstructed_content)}")
    print("reconstructed_content_preview:")
    print(reconstructed_content[:preview_chars])


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(
        run(
            url=args.url,
            token=args.token,
            page_id=args.page_id,
            username=args.username,
            password=args.password,
            otp_secret=args.otp_secret,
            preview_chars=args.preview_chars,
            output_txt=args.output_txt,
        )
    )


if __name__ == "__main__":
    main()
