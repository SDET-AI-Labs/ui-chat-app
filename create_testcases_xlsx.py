from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws.title = "Sheet1"
ws.append(["url", "expected_title"])
ws.append(["https://example.com", "Example Domain"])
wb.save("./data/testcases.xlsx")
