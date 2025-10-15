# 🌐 Hướng dẫn Batch Processing CV trên Web Interface

## 🎯 Tổng quan

Web interface đã được nâng cấp để hỗ trợ **batch processing 20+ CV cùng lúc** với các tính năng:

- ✅ **Real-time progress tracking** với progress bar động
- ✅ **Server-Sent Events** để cập nhật tiến độ ngay lập tức
- ✅ **Accordion UI** để hiển thị kết quả từng CV
- ✅ **Tự động sắp xếp** CV theo điểm số từ cao đến thấp
- ✅ **Hỗ trợ nhiều định dạng**: PDF, DOCX, DOC
- ✅ **Job requirements** tùy chọn để tính điểm AI

## 🚀 Cách sử dụng

### Bước 1: Khởi động Flask server

```bash
# Cài đặt dependencies (nếu chưa)
pip install -r requirements.txt

# Chạy Flask app
python app.py
```

Server sẽ chạy tại: `http://localhost:8000`

### Bước 2: Truy cập Web Interface

Mở trình duyệt và truy cập: `http://localhost:8000`

### Bước 3: Chọn chế độ Batch Processing

1. Click vào tab **"📚 Batch Processing (20+ CVs)"**
2. Giao diện batch processing sẽ hiển thị

### Bước 4: Upload CV files

1. Click vào **"📁 Select Multiple CV Files"**
2. Chọn nhiều file CV (PDF, DOCX, DOC) cùng lúc
3. Số lượng file đã chọn sẽ hiển thị: `Selected: X files`

### Bước 5: Nhập Job Requirements (Tùy chọn)

- Nếu muốn AI tính điểm cho CV, nhập job requirements vào textarea
- Nếu bỏ qua, CV sẽ chỉ được parse mà không có điểm số

Ví dụ job requirements:

```
Software Engineer Requirements:
- Bachelor's degree in Computer Science
- 3+ years experience in Python, JavaScript
- Experience with React, Node.js
- Knowledge of databases (SQL, MongoDB)
- Strong problem-solving skills
```

### Bước 6: Bắt đầu xử lý

1. Click **"🚀 Start Batch Processing"**
2. Progress bar sẽ hiển thị ngay lập tức

## 📊 Theo dõi tiến độ

### Progress Bar hiển thị:

```
⏳ Processing Progress
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
15 / 20 CVs processed        75%
Current: john_doe_resume.pdf
```

### Thông tin real-time:

- **Số CV đã xử lý / Tổng số CV**
- **Phần trăm hoàn thành**
- **File đang xử lý hiện tại**
- **Progress bar động** (cập nhật mỗi 0.5 giây)

## 🎉 Xem kết quả

### Khi hoàn thành, bạn sẽ thấy:

#### 1. Summary Statistics

```
┌─────────────┬─────────────┬─────────────┐
│  Total CVs  │  Completed  │   Failed    │
│     20      │     18      │      2      │
└─────────────┴─────────────┴─────────────┘
```

#### 2. Accordion List (Sắp xếp theo điểm)

Mỗi CV hiển thị dạng accordion:

```
▼ john_doe_resume.pdf  [✅ Success]  [87.5 / 100]
  ├─ 📊 AI Scores
  │  ├─ Education: 85
  │  ├─ Work Experience: 90
  │  ├─ Technical Skills: 88
  │  ├─ Certifications: 80
  │  ├─ Projects: 92
  │  └─ Languages & Skills: 85
  │
  └─ 📄 Parsed Resume Data
     └─ [JSON format với đầy đủ thông tin]
```

### Tính năng Accordion:

- **Click vào header** để mở/đóng chi tiết
- **Icon mũi tên** xoay khi mở/đóng
- **Màu sắc phân biệt**:
  - 🟢 Xanh: Success
  - 🔴 Đỏ: Failed
  - 🔵 Xanh dương: Score badge

## 🎨 UI Components

### Tab Navigation

```
┌──────────────┬──────────────────────────────┐
│ 📄 Single CV │ 📚 Batch Processing (20+ CVs) │
└──────────────┴──────────────────────────────┘
```

### Progress Bar

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[████████████████░░░░░░░░░░░░] 75%
```

### Accordion Item

```
┌─────────────────────────────────────────────┐
│ ▶ filename.pdf  [✅ Success]  [87.5 / 100]  │
├─────────────────────────────────────────────┤
│ (Click to expand/collapse)                   │
└─────────────────────────────────────────────┘
```

## 🔧 API Endpoints

### 1. `/batch_process` (POST)

**Mô tả**: Bắt đầu batch processing

**Request**:

- `pdf_docs`: Multiple files
- `job_requirements`: String (optional)

**Response**:

```json
{
	"message": "Batch processing started",
	"total_files": 20
}
```

### 2. `/batch_progress` (GET - Server-Sent Events)

**Mô tả**: Stream progress updates real-time

**Response Stream**:

```
data: {"completed": 5, "total": 20, "percentage": 25.0, "current_file": "cv5.pdf", "status": "processing"}

data: {"completed": 6, "total": 20, "percentage": 30.0, "current_file": "cv6.pdf", "status": "processing"}

...

data: {"completed": 20, "total": 20, "percentage": 100.0, "current_file": "", "status": "completed"}
```

### 3. `/batch_results` (GET)

**Mô tả**: Lấy kết quả cuối cùng

**Response**:

```json
{
  "status": "completed",
  "total": 20,
  "completed": 20,
  "results": [
    {
      "filename": "cv1.pdf",
      "status": "completed",
      "error": null,
      "parsed_data": {...},
      "scores": {...}
    },
    ...
  ]
}
```

## ⚡ Performance Tips

### 1. Số lượng CV khuyến nghị:

- **1-10 CV**: Rất nhanh (2-5 phút)
- **11-20 CV**: Nhanh (5-10 phút)
- **21-50 CV**: Trung bình (10-25 phút)
- **50+ CV**: Chậm (25+ phút)

### 2. Tối ưu hóa:

- Upload file có kích thước nhỏ hơn 5MB
- Sử dụng PDF text-based (không phải scan)
- Đảm bảo kết nối internet ổn định
- Không đóng tab browser khi đang xử lý

### 3. Rate Limiting:

- Gemini API có rate limit
- Nếu gặp lỗi 429, hãy đợi vài phút
- Code tự động xử lý từng CV tuần tự để tránh rate limit

## 🐛 Troubleshooting

### Lỗi: "Failed to start batch processing"

**Nguyên nhân**: Server không thể nhận file
**Giải pháp**:

- Kiểm tra file có đúng định dạng (PDF, DOCX, DOC)
- Đảm bảo file không bị corrupt
- Thử lại với ít file hơn

### Lỗi: Progress bar không cập nhật

**Nguyên nhân**: Server-Sent Events bị block
**Giải pháp**:

- Refresh trang và thử lại
- Kiểm tra console log (F12)
- Đảm bảo không có ad-blocker chặn SSE

### Lỗi: CV bị "Failed"

**Nguyên nhân**: Không thể extract text hoặc AI error
**Giải pháp**:

- Kiểm tra file CV có đúng định dạng
- Xem error message trong accordion
- Thử upload lại file đó riêng lẻ

### Progress bar bị "stuck"

**Nguyên nhân**: Server đang xử lý CV phức tạp
**Giải pháp**:

- Đợi thêm 1-2 phút
- Kiểm tra terminal log của Flask
- Nếu quá 5 phút không có tiến độ, refresh trang

## 📱 Responsive Design

Web interface hoạt động tốt trên:

- 💻 Desktop (Chrome, Firefox, Edge, Safari)
- 📱 Tablet (iPad, Android tablets)
- 📱 Mobile (iPhone, Android phones)

## 🎯 Best Practices

### 1. Chuẩn bị CV files:

- Đặt tên file rõ ràng: `nguyen_van_a_cv.pdf`
- Tránh ký tự đặc biệt trong tên file
- Đảm bảo CV có cấu trúc rõ ràng

### 2. Job Requirements:

- Viết rõ ràng, chi tiết
- Bao gồm: skills, experience, education
- Sử dụng bullet points

### 3. Xử lý kết quả:

- Xem CV có điểm cao nhất trước
- Lưu lại kết quả bằng cách copy JSON
- So sánh nhiều CV cùng lúc

## 🔐 Security Notes

- File upload được lưu tạm trong `__DATA__/batch/`
- File sẽ bị ghi đè trong lần xử lý tiếp theo
- Không lưu trữ CV lâu dài trên server
- Nên xóa file sau khi xử lý xong

## 📊 Example Workflow

```
1. User uploads 20 CVs + Job Requirements
   ↓
2. Server saves files to __DATA__/batch/
   ↓
3. Background thread starts processing
   ↓
4. Server-Sent Events stream progress to browser
   ↓
5. Browser updates progress bar real-time
   ↓
6. When completed, fetch results via /batch_results
   ↓
7. Display results in accordion format
   ↓
8. User reviews CVs sorted by score
```

## 🎉 Kết luận

Web interface batch processing giúp bạn:

- ⚡ Xử lý hàng loạt CV nhanh chóng
- 📊 Theo dõi tiến độ real-time
- 🎯 Tự động sắp xếp theo điểm số
- 📱 Sử dụng trên mọi thiết bị
- 🎨 Giao diện đẹp, dễ sử dụng

**Happy CV Processing! 🚀**

