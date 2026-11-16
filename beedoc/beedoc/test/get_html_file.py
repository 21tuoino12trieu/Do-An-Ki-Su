import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from beedoc_v3.readers.document_reader.confluence_html_reader import ConfluenceHtmlReader


async def run(args: argparse.Namespace) -> None:
    if not args.token or not args.page_id:
        raise ValueError("--token and --page-id are required.")

    from beedoc_v3.engine import BeedocEngine

    config = {
        "url": args.url,
        "token": args.token,
        "username": args.username or None,
        "password": args.password or None,
        "otp_secret": args.otp_secret or None,
    }
    reader = ConfluenceHtmlReader(
        url=args.url,
        token=args.token,
        username=args.username or None,
        password=args.password or None,
        otp_secret=args.otp_secret or None,
        bundle_root=args.bundle_root or None,
    )
    bundle = reader.export_page(args.page_id)

    engine = BeedocEngine(config=config)
    document = await engine.process(bundle["html_path"])

    markdown = str(document.reconstructed_content or "")
    output_path = Path(args.output_markdown).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    print(f"status: {document.status}")
    print(f"html_path: {bundle['html_path']}")
    print(f"bundle_dir: {bundle['bundle_dir']}")
    print(f"output_markdown: {output_path}")
    print(f"reconstructed_content_length: {len(markdown)}")
    if document.error_message:
        print(f"error: {document.error_message}")
    if args.preview_chars > 0:
        print("reconstructed_content_preview:")
        print(markdown[:args.preview_chars])

    await asyncio.sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a Confluence page to a local HTML bundle.")
    parser.add_argument("--url", default=os.getenv("CONFLUENCE_URL", "https://confluence.mbbank.com.vn"))
    parser.add_argument("--token", default=os.getenv("CONFLUENCE_TOKEN", "REPLACE_WITH_LOCAL_SECRET"))
    parser.add_argument("--username", default=os.getenv("CONFLUENCE_USERNAME", "aiplatform"))
    parser.add_argument("--password", default=os.getenv("CONFLUENCE_PASSWORD", "Rndai@2026!!"))
    parser.add_argument("--otp-secret", default=os.getenv("CONFLUENCE_OTP_SECRET", "REPLACE_WITH_LOCAL_SECRET"))
    parser.add_argument("--page-id", default=os.getenv("CONFLUENCE_PAGE_ID", "855250841"))
    parser.add_argument("--bundle-root", default=os.getenv("CONFLUENCE_BUNDLE_ROOT", ""))
    parser.add_argument("--output-markdown", default="assets/output_markdown.txt")
    parser.add_argument("--preview-chars", type=int, default=5000)
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
