# 🚀 Hướng dẫn Batch Processing CV - Xử lý nhiều CV cùng lúc

## 📋 Tổng quan

Code đã được cập nhật để hỗ trợ xử lý **nhiều CV cùng lúc** (tối đa 20+ CV) với các tính năng:

- ✅ Quét và phát hiện tự động các file CV trong thư mục
- ✅ Xử lý song song với multi-threading (3-5 threads)
- ✅ Hỗ trợ nhiều định dạng: PDF, DOCX, DOC, TXT, RTF
- ✅ Export kết quả ra Excel/CSV với đầy đủ thông tin
- ✅ Error handling và retry mechanism
- ✅ Progress tracking và báo cáo chi tiết

## 🛠️ Cài đặt

### 1. Cài đặt các thư viện cần thiết:

```bash
pip install -r requirements.txt
```

### 2. Cấu hình API Key:

Đảm bảo file `config.yaml` có cấu trúc:

```yaml
GEMINI_API_KEY: "your_gemini_api_key_here"
```

## 🎯 Cách sử dụng

### Phương pháp 1: Sử dụng function chính

```python
from resumeparser import batch_process_cvs

# Xử lý tất cả CV trong thư mục
results = batch_process_cvs(
    cv_folder_path="path/to/cv/folder",           # Đường dẫn thư mục chứa CV
    job_requirements="Software Engineer requirements",  # Yêu cầu công việc (tùy chọn)
    max_workers=5,                                # Số thread song song (3-5 là tốt nhất)
    output_format='excel'                         # 'excel' hoặc 'csv'
)
```

### Phương pháp 2: Sử dụng demo interactive

```python
from resumeparser import demo_batch_processing

# Chạy demo với input từ user
results = demo_batch_processing()
```

### Phương pháp 3: Sử dụng từng bước riêng lẻ

```python
from resumeparser import scan_cv_files, process_multiple_cvs, export_results_to_excel

# Bước 1: Quét file CV
cv_files = scan_cv_files("path/to/cv/folder")

# Bước 2: Xử lý batch
results = process_multiple_cvs(cv_files, job_requirements="", max_workers=3)

# Bước 3: Export kết quả
excel_file = export_results_to_excel(results)
```

## 📁 Cấu trúc thư mục

```
your_project/
├── resumeparser.py
├── config.yaml
├── requirements.txt
├── cv_samples/          # Thư mục chứa CV (20+ files)
│   ├── cv1.pdf
│   ├── cv2.docx
│   ├── cv3.txt
│   └── ...
└── output/              # Thư mục kết quả (tự tạo)
    ├── cv_analysis_results_20241201_143022.xlsx
    └── ...
```

## 📊 Kết quả output

### File Excel sẽ có 3 sheets:

1. **Tổng quan**: Thống kê điểm số và trạng thái của từng CV
2. **Chi tiết CV**: Nội dung đã parse của từng CV
3. **Yêu cầu công việc**: Job requirements (nếu có)

### Các cột trong sheet Tổng quan:

- Tên file
- Trạng thái (completed/failed)
- Thời gian xử lý
- Điểm tổng (0-100)
- Điểm học vấn, kinh nghiệm, kỹ năng, etc.
- Lỗi (nếu có)

## ⚡ Tối ưu hiệu suất

### Số thread khuyến nghị:

- **3-5 threads**: Tối ưu cho hầu hết trường hợp
- **1-2 threads**: Nếu gặp lỗi rate limit từ Gemini API
- **6+ threads**: Chỉ khi có API key mạnh và ít CV

### Thời gian xử lý ước tính:

- **1 CV**: 10-30 giây (tùy độ phức tạp)
- **20 CV**: 5-15 phút (với 3-5 threads)

## 🔧 Xử lý lỗi thường gặp

### 1. Lỗi import thư viện:

```bash
# Cài đặt lại thư viện
pip install PyPDF2 python-docx pandas openpyxl
```

### 2. Lỗi rate limit Gemini API:

- Giảm số `max_workers` xuống 1-2
- Thêm delay giữa các request

### 3. Lỗi đọc file PDF/DOCX:

- Kiểm tra file không bị corrupt
- Đảm bảo file không có password protection

### 4. Lỗi encoding:

- File TXT nên dùng UTF-8 encoding
- Code đã tự động thử nhiều encoding

## 📈 Monitoring và Debug

### Theo dõi tiến độ:

```
🔍 Đang quét thư mục: cv_samples
✅ Tìm thấy: cv1.pdf
✅ Tìm thấy: cv2.docx
📊 Tổng cộng tìm thấy 20 file CV

🚀 Bắt đầu xử lý 20 CV với 3 threads...
🔄 Xử lý CV 1/3: cv1.pdf
✅ Hoàn thành: cv1.pdf (thời gian: 15.23s)
📊 Tiến độ: 1/20 (5.0%)
```

### Tóm tắt cuối:

```
📊 TÓM TẮT KẾT QUẢ XỬ LÝ BATCH CV
============================================================
📁 Tổng số CV: 20
✅ Thành công: 18
❌ Thất bại: 2
⏱️  Tổng thời gian: 245.67 giây
⏱️  Thời gian trung bình: 12.28 giây/CV
📈 Tỷ lệ thành công: 90.0%
🏆 CV tốt nhất: cv5.pdf (điểm: 87.5)
```

## 🎯 Ví dụ thực tế

```python
# Ví dụ xử lý 20 CV cho vị trí Software Engineer
job_req = """
Software Engineer Requirements:
- Bachelor's degree in Computer Science or related field
- 3+ years experience in Python, JavaScript, React
- Experience with databases (SQL, MongoDB)
- Knowledge of cloud platforms (AWS, Azure)
- Strong problem-solving skills
- English proficiency
"""

results = batch_process_cvs(
    cv_folder_path="cv_applications",
    job_requirements=job_req,
    max_workers=4,
    output_format='excel'
)

print(f"Đã xử lý {len(results)} CV thành công!")
```

## 🔄 Tự động hóa

Bạn có thể tạo script để chạy định kỳ:

```python
import schedule
import time
from resumeparser import batch_process_cvs

def daily_cv_processing():
    results = batch_process_cvs(
        cv_folder_path="new_applications",
        job_requirements="Your job requirements",
        max_workers=3
    )
    print(f"Đã xử lý {len(results)} CV mới")

# Chạy mỗi ngày lúc 9h sáng
schedule.every().day.at("09:00").do(daily_cv_processing)

while True:
    schedule.run_pending()
    time.sleep(60)
```

## 📞 Hỗ trợ

Nếu gặp vấn đề, hãy kiểm tra:

1. File `config.yaml` có đúng format
2. API key Gemini có hoạt động
3. Các thư viện đã được cài đặt đầy đủ
4. Thư mục CV tồn tại và có quyền đọc

---

**🎉 Chúc bạn thành công với batch processing CV!**

