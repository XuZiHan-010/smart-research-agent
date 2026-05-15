#!/usr/bin/env python3
"""Test PDF generation"""

from backend.services.pdf_service import PDFService

# Sample markdown report
test_report = """# 中国新能源汽车市场

**Date**: 2024-01-15

## 市场概述

这是一份测试报告。

### 关键数据
- 数据点1
- 数据点2
- 数据点3

## 竞争格局

主要竞争对手包括：
1. Tesla
2. 比亚迪
3. 小鹏汽车

## 结论

这是测试结论。
"""

print("Testing PDF generation...")
service = PDFService()
ok, result = service.generate_pdf_bytes(test_report, "中国新能源汽车市场", language="zh")

if ok:
    print(f"OK - PDF generation successful! File size: {len(result)} bytes")
    # Write to test file
    with open("test_report.pdf", "wb") as f:
        f.write(result)
    print("OK - Written to test_report.pdf")
else:
    print(f"ERROR - PDF generation failed: {result}")
