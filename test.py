import os
from getpass import getpass

from atlassian import ConfluenceV2


def main():
    # api_token = os.getenv("CONFLUENCE_API_TOKEN") or getpass("Confluence API token: ")
    confluence = ConfluenceV2(
        url="https://doantotnghiep2026.atlassian.net/wiki",
        username=os.getenv("CONFLUENCE_EMAIL", "dangnamcuong29112003@gmail.com"),
        password="REPLACE_WITH_LOCAL_SECRET",
        timeout=30,
    )

    page_id = "7274499"
    page = confluence.get_page_by_id(page_id, body_format="storage")

    print("Title:", page["title"])
    print("Content:", page["body"]["storage"]["value"])


if __name__ == "__main__":
    main()
