# 🚀 Resume Parser with Batch Processing

## 📋 Tổng quan

Hệ thống Resume Parser đã được nâng cấp với khả năng **xử lý hàng loạt nhiều CV cùng lúc** (20+ CV) với 2 phương thức:

1. **🌐 Web Interface** - Giao diện web với progress tracking real-time
2. **💻 Command Line** - Script Python để xử lý batch offline

## ✨ Tính năng chính

### Web Interface

- ✅ Upload nhiều CV cùng lúc (PDF, DOCX, DOC)
- ✅ Progress bar real-time với Server-Sent Events
- ✅ Accordion UI để xem kết quả từng CV
- ✅ Tự động sắp xếp theo điểm số
- ✅ Responsive design (Desktop, Tablet, Mobile)
- ✅ Job requirements tùy chọn

### Command Line

- ✅ Quét thư mục tự động
- ✅ Multi-threading (3-5 threads)
- ✅ Export Excel/CSV
- ✅ Error handling & retry
- ✅ Progress tracking
- ✅ Detailed summary report

## 🛠️ Cài đặt

### 1. Clone repository

```bash
git clone <your-repo>
cd Resume-Parser-OpenAI
```

### 2. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 3. Cấu hình API Key

Tạo file `config.yaml`:

```yaml
GEMINI_API_KEY: "your_gemini_api_key_here"
```

## 🌐 Sử dụng Web Interface

### Khởi động server:

```bash
python app.py
```

### Truy cập:

```
http://localhost:8000
```

### Các bước:

1. Click tab **"📚 Batch Processing (20+ CVs)"**
2. Chọn nhiều file CV
3. Nhập job requirements (tùy chọn)
4. Click **"🚀 Start Batch Processing"**
5. Theo dõi progress bar real-time
6. Xem kết quả trong accordion

**Chi tiết**: Xem [WEB_BATCH_PROCESSING_GUIDE.md](WEB_BATCH_PROCESSING_GUIDE.md)

## 💻 Sử dụng Command Line

### Cách 1: Sử dụng function chính

```python
from resumeparser import batch_process_cvs

results = batch_process_cvs(
    cv_folder_path="path/to/cv/folder",
    job_requirements="Software Engineer requirements",
    max_workers=3,
    output_format='excel'
)
```

### Cách 2: Sử dụng demo interactive

```python
from resumeparser import demo_batch_processing

results = demo_batch_processing()
```

### Cách 3: Từng bước riêng lẻ

```python
from resumeparser import scan_cv_files, process_multiple_cvs, export_results_to_excel

# Quét file
cv_files = scan_cv_files("cv_folder")

# Xử lý batch
results = process_multiple_cvs(cv_files, job_requirements="", max_workers=3)

# Export Excel
export_results_to_excel(results)
```

**Chi tiết**: Xem [BATCH_PROCESSING_GUIDE.md](BATCH_PROCESSING_GUIDE.md)

## 📁 Cấu trúc thư mục

```
Resume-Parser-OpenAI/
├── app.py                          # Flask web application
├── resumeparser.py                 # Core parsing + batch functions
├── config.yaml                     # API key configuration
├── requirements.txt                # Python dependencies
│
├── templates/
│   └── index.html                  # Web interface với batch UI
│
├── __DATA__/                       # Upload directory
│   └── batch/                      # Batch upload files
│
├── output/                         # Kết quả batch processing
│   └── cv_analysis_results_*.xlsx
│
├── BATCH_PROCESSING_GUIDE.md       # Hướng dẫn CLI
├── WEB_BATCH_PROCESSING_GUIDE.md   # Hướng dẫn Web
├── DEMO_SCREENSHOTS.md             # Demo mockups
└── README_BATCH_PROCESSING.md      # File này
```

## 📊 Output Format

### Excel File (3 sheets):

1. **Tổng quan**: Điểm số và trạng thái
2. **Chi tiết CV**: Nội dung đã parse
3. **Yêu cầu công việc**: Job requirements

### CSV File:

- Tổng quan điểm số và trạng thái

### Web Interface:

- Summary statistics
- Accordion với từng CV
- Real-time progress

## 🎯 Ví dụ thực tế

### Scenario: Tuyển dụng Software Engineer

**Bước 1**: Chuẩn bị 20 CV trong thư mục `applications/`

**Bước 2**: Định nghĩa job requirements

```python
job_req = """
Software Engineer Requirements:
- Bachelor's degree in Computer Science
- 3+ years experience in Python, JavaScript
- Experience with React, Node.js
- Knowledge of databases (SQL, MongoDB)
- Strong problem-solving skills
- English proficiency
"""
```

**Bước 3**: Xử lý batch

```python
results = batch_process_cvs(
    cv_folder_path="applications",
    job_requirements=job_req,
    max_workers=4,
    output_format='excel'
)
```

**Bước 4**: Xem kết quả

```
📊 TÓM TẮT KẾT QUẢ XỬ LÝ BATCH CV
============================================================
📁 Tổng số CV: 20
✅ Thành công: 18
❌ Thất bại: 2
⏱️  Tổng thời gian: 245.67 giây
⏱️  Thời gian trung bình: 12.28 giây/CV
📈 Tỷ lệ thành công: 90.0%
🏆 CV tốt nhất: nguyen_van_a.pdf (điểm: 92.5)
```

## ⚡ Performance

### Thời gian xử lý ước tính:

| Số CV | Thời gian (3 threads) | Thời gian (5 threads) |
| ----- | --------------------- | --------------------- |
| 5     | 2-3 phút              | 1-2 phút              |
| 10    | 4-6 phút              | 3-4 phút              |
| 20    | 8-12 phút             | 6-8 phút              |
| 50    | 20-30 phút            | 15-20 phút            |

### Tối ưu hóa:

- **3-5 threads**: Tối ưu cho hầu hết trường hợp
- **1-2 threads**: Nếu gặp rate limit
- **6+ threads**: Chỉ khi có API key mạnh

## 🔧 API Endpoints (Web)

### POST `/batch_process`

Bắt đầu batch processing

**Request**:

- `pdf_docs`: Multiple files
- `job_requirements`: String (optional)

### GET `/batch_progress` (SSE)

Stream progress updates real-time

### GET `/batch_results`

Lấy kết quả cuối cùng

## 🐛 Troubleshooting

### Lỗi import thư viện

```bash
pip install PyPDF2 python-docx pandas openpyxl
```

### Lỗi rate limit Gemini API

- Giảm `max_workers` xuống 1-2
- Thêm delay giữa requests

### Lỗi đọc file

- Kiểm tra file không corrupt
- Đảm bảo không có password protection
- Thử encoding khác

### Progress bar không cập nhật (Web)

- Refresh trang
- Kiểm tra console log (F12)
- Đảm bảo không có ad-blocker

## 📚 Documentation

- [BATCH_PROCESSING_GUIDE.md](BATCH_PROCESSING_GUIDE.md) - Hướng dẫn CLI chi tiết
- [WEB_BATCH_PROCESSING_GUIDE.md](WEB_BATCH_PROCESSING_GUIDE.md) - Hướng dẫn Web chi tiết
- [DEMO_SCREENSHOTS.md](DEMO_SCREENSHOTS.md) - Demo mockups

## 🔐 Security

- File upload được lưu tạm trong `__DATA__/batch/`
- File sẽ bị ghi đè trong lần xử lý tiếp theo
- Không lưu trữ CV lâu dài trên server
- Nên xóa file sau khi xử lý xong

## 🎨 Tech Stack

### Backend:

- **Flask** - Web framework
- **Google Gemini AI** - Resume parsing & scoring
- **Threading** - Parallel processing
- **Server-Sent Events** - Real-time progress

### Frontend:

- **HTML5** - Structure
- **Tailwind CSS** - Styling
- **Vanilla JavaScript** - Interactivity
- **EventSource API** - SSE client

### Data Processing:

- **PyPDF2** - PDF extraction
- **python-docx** - DOCX extraction
- **pandas** - Data manipulation
- **openpyxl** - Excel export

## 📈 Roadmap

### Planned Features:

- [ ] Export to PDF report
- [ ] Email notification when completed
- [ ] Database storage for results
- [ ] Advanced filtering & sorting
- [ ] Comparison view (side-by-side)
- [ ] Custom scoring weights
- [ ] Multi-language support
- [ ] Docker containerization

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Open Pull Request

## 📄 License

MIT License - See LICENSE file

## 👥 Authors

- Your Name - Initial work

## 🙏 Acknowledgments

- Google Gemini AI for powerful NLP
- Flask community
- Tailwind CSS team

## 📞 Support

For issues or questions:

- Open an issue on GitHub
- Email: your.email@example.com

---

**🎉 Happy CV Processing!**

Made with ❤️ using Python, Flask, and Google Gemini AI

