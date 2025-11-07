import json
from pathlib import Path

from openpyxl import Workbook


def main() -> None:
    base_dir = Path(__file__).parent
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    xlsx_path = data_dir / "api_tests.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "api_tests"

    # Columns per domain-standard: method, url, expected_field, expected_value, body, headers, status
    ws.append([
        "method",
        "url",
        "expected_field",
        "expected_value",
        "body",
        "headers",
        "status",
    ])

    # Row 1: GET https://jsonplaceholder.typicode.com/todos/1 → expect title "delectus aut autem"
    ws.append([
        "GET",
        "https://jsonplaceholder.typicode.com/todos/1",
        "title",
        "delectus aut autem",
        "",
        "",
        "",
    ])

    # Row 2: GET .../todos/2 → expect id 2
    ws.append([
        "GET",
        "https://jsonplaceholder.typicode.com/todos/2",
        "id",
        "2",
        "",
        "",
        "",
    ])

    # Row 3: POST .../posts → expect title echoed back; provide JSON body and header
    post_body = {"title": "foo", "body": "bar", "userId": 1}
    post_headers = {"Content-Type": "application/json"}
    ws.append([
        "POST",
        "https://jsonplaceholder.typicode.com/posts",
        "title",
        "foo",
        json.dumps(post_body),
        json.dumps(post_headers),
        "",
    ])

    # Row 4: GET .../posts/1 → expect userId 1
    ws.append([
        "GET",
        "https://jsonplaceholder.typicode.com/posts/1",
        "userId",
        "1",
        "",
        "",
        "",
    ])

    wb.save(xlsx_path)
    print(f"Wrote {xlsx_path}")


if __name__ == "__main__":
    main()
