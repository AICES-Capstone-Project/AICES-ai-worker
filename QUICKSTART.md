# ⚡ Quick Start - Batch Processing CV

## 🚀 5 phút để bắt đầu!

### Bước 1: Cài đặt (1 phút)

```bash
pip install -r requirements.txt
```

### Bước 2: Cấu hình API Key (30 giây)

Tạo file `config.yaml`:

```yaml
GEMINI_API_KEY: "your_api_key_here"
```

### Bước 3: Chọn phương thức

---

## 🌐 PHƯƠNG THỨC 1: Web Interface (Khuyến nghị)

### Khởi động server:

```bash
python app.py
```

### Sử dụng:

1. Mở browser: `http://localhost:8000`
2. Click tab **"📚 Batch Processing (20+ CVs)"**
3. Chọn nhiều file CV
4. (Tùy chọn) Nhập job requirements
5. Click **"🚀 Start Batch Processing"**
6. Xem progress bar real-time
7. Xem kết quả trong accordion

**✨ Ưu điểm:**

- Giao diện đẹp, dễ sử dụng
- Progress bar real-time
- Xem kết quả ngay trên web
- Không cần code

---

## 💻 PHƯƠNG THỨC 2: Command Line

### Cách nhanh nhất:

```python
from resumeparser import batch_process_cvs

results = batch_process_cvs(
    cv_folder_path="path/to/cv/folder",
    job_requirements="Your job requirements here",
    max_workers=3,
    output_format='excel'
)
```

### Hoặc dùng demo interactive:

```python
from resumeparser import demo_batch_processing
demo_batch_processing()
```

**✨ Ưu điểm:**

- Tự động hóa hoàn toàn
- Export Excel/CSV
- Phù hợp cho script automation

---

## 📊 Kết quả

### Web Interface:

- Summary statistics (Total, Success, Failed)
- Accordion list với từng CV
- Sắp xếp theo điểm số
- Xem chi tiết từng CV

### Command Line:

- File Excel với 3 sheets:
  - Tổng quan (điểm số)
  - Chi tiết CV (parsed data)
  - Job requirements
- Lưu trong thư mục `output/`

---

## 🎯 Ví dụ nhanh

### Xử lý 20 CV cho vị trí Software Engineer:

**Web**:

1. Upload 20 files
2. Paste job requirements
3. Click Start
4. Đợi 5-10 phút
5. Xem kết quả

**CLI**:

```python
from resumeparser import batch_process_cvs

results = batch_process_cvs(
    cv_folder_path="applications",
    job_requirements="""
    Software Engineer Requirements:
    - Bachelor's in CS
    - 3+ years Python/JavaScript
    - React, Node.js experience
    """,
    max_workers=3
)
```

---

## ⚡ Tips

### Tốc độ:

- 3-5 threads = Tối ưu
- 1 CV ≈ 10-30 giây
- 20 CV ≈ 5-15 phút

### File formats:

- ✅ PDF (text-based)
- ✅ DOCX
- ✅ DOC
- ❌ Scanned PDF (không tốt)
- ❌ Images

### Best practices:

- File < 5MB
- Tên file rõ ràng
- CV có cấu trúc tốt
- Job requirements chi tiết

---

## 🐛 Lỗi thường gặp

### "Module not found"

```bash
pip install -r requirements.txt
```

### "API key error"

- Kiểm tra `config.yaml`
- Đảm bảo API key đúng

### "Cannot extract text"

- File bị corrupt
- File có password
- Scanned PDF (không có text layer)

### Progress bar không cập nhật

- Refresh trang
- Kiểm tra console (F12)

---

## 📚 Tài liệu đầy đủ

- [WEB_BATCH_PROCESSING_GUIDE.md](WEB_BATCH_PROCESSING_GUIDE.md) - Web interface
- [BATCH_PROCESSING_GUIDE.md](BATCH_PROCESSING_GUIDE.md) - Command line
- [README_BATCH_PROCESSING.md](README_BATCH_PROCESSING.md) - Tổng quan

---

## 🎉 Bắt đầu ngay!

### Web (Dễ nhất):

```bash
python app.py
# Mở http://localhost:8000
```

### CLI (Nhanh nhất):

```python
from resumeparser import demo_batch_processing
demo_batch_processing()
```

**Happy CV Processing! 🚀**


