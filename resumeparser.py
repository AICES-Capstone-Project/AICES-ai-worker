# import libraries

import google.generativeai as genai
import yaml

api_key = None
CONFIG_PATH = r"config.yaml"

with open(CONFIG_PATH) as file:
    data = yaml.load(file, Loader=yaml.FullLoader)
    api_key = data['GEMINI_API_KEY']
    
# Configure Gemini
genai.configure(api_key=api_key)

# def list_available_models():
#     """List all available Gemini models"""
#     print("🔍 Đang tải danh sách các model Gemini có sẵn...\n")
    
#     try:
#         models = genai.list_models()
#         print("📋 DANH SÁCH CÁC MODEL GEMINI CÓ SẴN:\n")
#         print("-" * 80)
        
#         for model in models:
#             model_name = model.name
#             display_name = model.display_name
#             supported_methods = model.supported_generation_methods
            
#             print(f"🏷️  Model Name: {model_name}")
#             print(f"📝 Display Name: {display_name}")
#             print(f"🔧 Supported Methods: {', '.join(supported_methods)}")
#             print("-" * 80)
#             print()
            
#     except Exception as e:
#         print(f"❌ Lỗi: {e}")

# Uncomment dòng dưới để xem danh sách models
# list_available_models()

def ats_extractor(resume_data):

    prompt = '''
        You are an AI bot specialized in parsing resumes for software recruitment purposes. 
        You will receive the plain text of a resume and must extract the most relevant information in a structured way.

        Your goal is to output ONLY a valid JSON object (no extra text, comments, or markdown). 
        Each field should contain a clean summary or structured JSON if possible.

        Extract and fill the following fields:

        {
            "info": "string / JSON or null",               # Basic details: full name, title, location, email, phone, LinkedIn
            "education": "string / JSON or null",          # Degrees, universities, graduation year, and major field
            "work_experience": "string / JSON or null",    # Job titles, companies, durations, responsibilities, and key results
            "technical_skills": "string / JSON or null",   # Programming languages, frameworks, tools, and technologies
            "certifications": "string / JSON or null",     # Professional certificates (e.g., AWS, PMP)
            "projects": "string / JSON or null",           # Notable projects, including technologies and outcomes
            "languages_and_skills": "string / JSON or null" # Spoken languages, soft skills, and interpersonal abilities
        }

        Rules:
        1. Return ONLY a valid JSON object — do not include explanations or text outside the JSON.
        2. If information is missing or unclear, use null for that field.
        3. Normalize bullet points and line breaks into readable sentences.
        4. When possible, convert structured sections (like skills or education) into JSON arrays or key-value form.
        5. Keep field content concise and factual — avoid assumptions.

        Return ONLY the JSON object, nothing else.
    '''

    # Initialize Gemini model - using the latest stable model
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    
    # Combine prompt with resume data
    full_prompt = f"{prompt}\n\nResume content:\n{resume_data}"
    
    try:
        # Generate response
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                max_output_tokens=8192, 
            )
        )
        
        # Extract text from Gemini response - FIXED
        data = ""
        
        try:
            # Check if response was blocked
            if hasattr(response, 'prompt_feedback'):
                print(f"⚠️  Prompt feedback: {response.prompt_feedback}")
            
            # Use response.parts as recommended by Gemini API
            if hasattr(response, 'parts') and response.parts:
                text_parts = []
                for part in response.parts:
                    if hasattr(part, 'text') and part.text:
                        text_parts.append(part.text)
                data = ''.join(text_parts).strip()
                # print(f"✅ SUCCESS using .parts: Extracted {len(data)} characters")
                # print(f"📄 First 200 chars: {data[:200]}...")
            # Fallback to candidates approach
            elif response.candidates:
                candidate = response.candidates[0]
                print(f"🔍 Candidate finish_reason: {candidate.finish_reason}")
                print(f"🔍 Candidate safety_ratings: {candidate.safety_ratings}")
                
                if candidate.content and candidate.content.parts:
                    # Extract text from all parts
                    text_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
                    data = ''.join(text_parts).strip()
                    print(f"✅ SUCCESS using candidates: Extracted {len(data)} characters")
                    # print(f"📄 First 200 chars: {data[:200]}...")
                else:
                    print("❌ No content.parts found in candidate")
                    print(f"🔍 Full candidate: {candidate}")
            else:
                print("❌ No candidates found in response")
                
        except Exception as e:
            print(f"❌ Error extracting text: {e}")
            import traceback
            traceback.print_exc()
        
        # Clean up the response to ensure it's valid JSON
        # Remove any markdown code blocks if present
        if data.startswith('```json'):
            data = data[7:]  # Remove ```json
        if data.startswith('```'):
            data = data[3:]   # Remove ```
        if data.endswith('```'):
            data = data[:-3]  # Remove trailing ```
        
        data = data.strip()
        
        # print(f"Raw response: {data}")  # Debug print
        
        return data
        
    except Exception as e:
        print(f"Error in ats_extractor: {e}")
        # Return a default JSON structure if there's an error
        return '''{
            "info": "null",             
            "education": "null",           
            "work_experience": "null",    
            "technical_skills": "null",    
            "certifications": "null",     
            "projects": "null",           
            "languages_and_skills": "null" 
        }'''


def ai_score_calculator(parsed_resume, job_requirements):
    """
    Calculate AI-based resume score by comparing parsed resume data with job requirements.
    
    Args:
        parsed_resume (dict): The parsed resume data from ats_extractor
        job_requirements (str or dict): Job description or requirements
        
    Returns:
        dict: Scores for each category, total weighted score, and AI explanations
    """
    
    prompt = f'''
    You are an AI resume evaluator. Your task is to score a candidate's resume against job requirements.
    
    SCORING INSTRUCTIONS:
    - Rate each category from 0 to 100
    - 0-40: Poor/Insufficient
    - 41-60: Below average/Needs improvement
    - 61-75: Average/Adequate
    - 76-85: Good/Strong
    - 86-100: Excellent/Outstanding
    
    JOB REQUIREMENTS:
    {job_requirements}
    
    CANDIDATE'S RESUME DATA:
    {parsed_resume}
    
    EVALUATE THE FOLLOWING CATEGORIES:
    1. **education** (0-100): Assess how well the candidate's educational background matches the job requirements
    2. **work_experience** (0-100): Evaluate relevant work experience, job titles, responsibilities, and achievements
    3. **technical_skills** (0-100): Rate the match of programming languages, frameworks, tools, and technologies
    4. **certifications** (0-100): Score professional certifications relevant to the job
    5. **projects** (0-100): Assess the relevance and quality of projects
    6. **languages_and_skills** (0-100): Evaluate soft skills, languages, and interpersonal abilities
    
    OUTPUT REQUIREMENTS:
    Return ONLY a valid JSON object with this exact structure (no markdown, no extra text):
    {{
        "education_score": <number 0-100>,
        "work_experience_score": <number 0-100>,
        "technical_skills_score": <number 0-100>,
        "certifications_score": <number 0-100>,
        "projects_score": <number 0-100>,
        "languages_and_skills_score": <number 0-100>,
        "AIExplanation": {{
            "education": "<brief 1-2 sentence explanation>",
            "work_experience": "<brief 1-2 sentence explanation>",
            "technical_skills": "<brief 1-2 sentence explanation>",
            "certifications": "<brief 1-2 sentence explanation>",
            "projects": "<brief 1-2 sentence explanation>",
            "languages_soft": "<brief 1-2 sentence explanation>"
        }}
    }}
    
    Be objective and fair in your evaluation. Return ONLY the JSON, nothing else.
    '''
    
    # Initialize Gemini model
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    
    try:
        # Generate response
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0,  # Slightly higher for more varied scoring
                max_output_tokens=4096,
            )
        )
        
        # Extract text from response
        data = ""
        if hasattr(response, 'parts') and response.parts:
            text_parts = []
            for part in response.parts:
                if hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)
            data = ''.join(text_parts).strip()
        elif response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                text_parts = []
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        text_parts.append(part.text)
                data = ''.join(text_parts).strip()
        
        # Clean up markdown code blocks if present
        if data.startswith('```json'):
            data = data[7:]
        if data.startswith('```'):
            data = data[3:]
        if data.endswith('```'):
            data = data[:-3]
        
        data = data.strip()
        
        # Parse the JSON response
        import json
        scores = json.loads(data)
        
        # Calculate total weighted score
        weights = {
            "education": 0.15,
            "work_experience": 0.25,
            "technical_skills": 0.35,
            "certifications": 0.05,
            "projects": 0.15,
            "languages_and_skills": 0.05
        }
        
        total_score = (
            scores.get("education_score", 0) * weights["education"] +
            scores.get("work_experience_score", 0) * weights["work_experience"] +
            scores.get("technical_skills_score", 0) * weights["technical_skills"] +
            scores.get("certifications_score", 0) * weights["certifications"] +
            scores.get("projects_score", 0) * weights["projects"] +
            scores.get("languages_and_skills_score", 0) * weights["languages_and_skills"]
        )
        
        # Add total_score to the response
        scores["total_score"] = round(total_score, 2)
        
        return scores
        
    except Exception as e:
        print(f"Error in ai_score_calculator: {e}")
        import traceback
        traceback.print_exc()
        
        # Return default scores on error
        return {
            "education_score": 0,
            "work_experience_score": 0,
            "technical_skills_score": 0,
            "certifications_score": 0,
            "projects_score": 0,
            "languages_and_skills_score": 0,
            "total_score": 0,
            "AIExplanation": {
                "education": "Error occurred during scoring",
                "work_experience": "Error occurred during scoring",
                "technical_skills": "Error occurred during scoring",
                "certifications": "Error occurred during scoring",
                "projects": "Error occurred during scoring",
                "languages_soft": "Error occurred during scoring"
            },
            "error": str(e)
        }


# =============================================================================
# BATCH PROCESSING FUNCTIONS FOR MULTIPLE CVs
# =============================================================================

import os
import pandas as pd
import time
from datetime import datetime
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


def get_supported_file_types():
    """Trả về danh sách các loại file CV được hỗ trợ"""
    return ['.pdf', '.docx', '.doc', '.txt', '.rtf']


def scan_cv_files(folder_path):
    """
    Quét thư mục để tìm tất cả file CV hợp lệ
    
    Args:
        folder_path (str): Đường dẫn đến thư mục chứa CV
        
    Returns:
        list: Danh sách đường dẫn file CV
    """
    if not os.path.exists(folder_path):
        print(f"❌ Thư mục không tồn tại: {folder_path}")
        return []
    
    supported_types = get_supported_file_types()
    cv_files = []
    
    print(f"🔍 Đang quét thư mục: {folder_path}")
    
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path):
            _, ext = os.path.splitext(filename.lower())
            if ext in supported_types:
                cv_files.append(file_path)
                print(f"✅ Tìm thấy: {filename}")
    
    print(f"📊 Tổng cộng tìm thấy {len(cv_files)} file CV")
    return cv_files


def extract_text_from_file(file_path):
    """
    Trích xuất text từ file CV (hỗ trợ nhiều định dạng)
    
    Args:
        file_path (str): Đường dẫn đến file CV
        
    Returns:
        str: Nội dung text của CV
    """
    _, ext = os.path.splitext(file_path.lower())
    
    try:
        if ext == '.pdf':
            # Cần cài đặt: pip install PyPDF2
            try:
                import PyPDF2
                with open(file_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                return text.strip()
            except ImportError:
                print("⚠️  PyPDF2 chưa được cài đặt. Chạy: pip install PyPDF2")
                return ""
        
        elif ext in ['.docx']:
            # Cần cài đặt: pip install python-docx
            try:
                from docx import Document
                doc = Document(file_path)
                text = ""
                for paragraph in doc.paragraphs:
                    text += paragraph.text + "\n"
                return text.strip()
            except ImportError:
                print("⚠️  python-docx chưa được cài đặt. Chạy: pip install python-docx")
                return ""
        
        elif ext in ['.doc']:
            # Cần cài đặt: pip install python-docx2txt
            try:
                import docx2txt
                return docx2txt.process(file_path)
            except ImportError:
                print("⚠️  docx2txt chưa được cài đặt. Chạy: pip install docx2txt")
                return ""
        
        elif ext in ['.txt', '.rtf']:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    return file.read().strip()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='latin-1') as file:
                        return file.read().strip()
                except:
                    return ""
        
        else:
            print(f"⚠️  Định dạng file không được hỗ trợ: {ext}")
            return ""
            
    except Exception as e:
        print(f"❌ Lỗi khi đọc file {file_path}: {e}")
        return ""


def process_single_cv(file_path, job_requirements="", max_retries=3):
    """
    Xử lý một CV đơn lẻ với retry mechanism
    
    Args:
        file_path (str): Đường dẫn đến file CV
        job_requirements (str): Yêu cầu công việc để tính điểm
        max_retries (int): Số lần thử lại tối đa
        
    Returns:
        dict: Kết quả xử lý CV
    """
    filename = os.path.basename(file_path)
    result = {
        'filename': filename,
        'file_path': file_path,
        'status': 'pending',
        'parsed_data': None,
        'scores': None,
        'error': None,
        'processing_time': 0
    }
    
    start_time = time.time()
    
    for attempt in range(max_retries):
        try:
            print(f"🔄 Xử lý CV {attempt + 1}/{max_retries}: {filename}")
            
            # Bước 1: Trích xuất text từ file
            resume_text = extract_text_from_file(file_path)
            if not resume_text:
                result['error'] = "Không thể trích xuất text từ file"
                result['status'] = 'failed'
                break
            
            # Bước 2: Parse CV với AI
            parsed_data = ats_extractor(resume_text)
            if not parsed_data:
                result['error'] = "AI không thể parse CV"
                result['status'] = 'failed'
                break
            
            # Bước 3: Tính điểm (nếu có job requirements)
            scores = None
            if job_requirements:
                scores = ai_score_calculator(parsed_data, job_requirements)
            
            # Thành công
            result['parsed_data'] = parsed_data
            result['scores'] = scores
            result['status'] = 'completed'
            result['processing_time'] = time.time() - start_time
            
            print(f"✅ Hoàn thành: {filename} (thời gian: {result['processing_time']:.2f}s)")
            break
            
        except Exception as e:
            print(f"❌ Lỗi lần {attempt + 1} khi xử lý {filename}: {e}")
            if attempt == max_retries - 1:
                result['error'] = str(e)
                result['status'] = 'failed'
                result['processing_time'] = time.time() - start_time
    
    return result


def process_multiple_cvs(cv_files, job_requirements="", max_workers=3, output_folder="output"):
    """
    Xử lý nhiều CV cùng lúc với threading
    
    Args:
        cv_files (list): Danh sách đường dẫn file CV
        job_requirements (str): Yêu cầu công việc để tính điểm
        max_workers (int): Số thread tối đa để xử lý song song
        output_folder (str): Thư mục lưu kết quả
        
    Returns:
        list: Danh sách kết quả xử lý tất cả CV
    """
    print(f"🚀 Bắt đầu xử lý {len(cv_files)} CV với {max_workers} threads...")
    
    # Tạo thư mục output nếu chưa có
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    results = []
    completed_count = 0
    total_count = len(cv_files)
    
    # Sử dụng ThreadPoolExecutor để xử lý song song
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tất cả tasks
        future_to_cv = {
            executor.submit(process_single_cv, cv_file, job_requirements): cv_file 
            for cv_file in cv_files
        }
        
        # Xử lý kết quả khi hoàn thành
        for future in as_completed(future_to_cv):
            cv_file = future_to_cv[future]
            try:
                result = future.result()
                results.append(result)
                completed_count += 1
                
                # Hiển thị progress
                progress = (completed_count / total_count) * 100
                print(f"📊 Tiến độ: {completed_count}/{total_count} ({progress:.1f}%)")
                
            except Exception as e:
                print(f"❌ Lỗi không mong muốn khi xử lý {cv_file}: {e}")
                results.append({
                    'filename': os.path.basename(cv_file),
                    'file_path': cv_file,
                    'status': 'failed',
                    'error': str(e),
                    'processing_time': 0
                })
                completed_count += 1
    
    # Sắp xếp kết quả theo filename
    results.sort(key=lambda x: x['filename'])
    
    print(f"🎉 Hoàn thành xử lý {len(results)} CV!")
    return results


def export_results_to_excel(results, output_folder="output", job_requirements=""):
    """
    Export kết quả xử lý CV ra file Excel
    
    Args:
        results (list): Danh sách kết quả xử lý CV
        output_folder (str): Thư mục lưu file Excel
        job_requirements (str): Yêu cầu công việc (để ghi vào file)
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_file = os.path.join(output_folder, f"cv_analysis_results_{timestamp}.xlsx")
    
    print(f"📊 Đang export kết quả ra Excel: {excel_file}")
    
    # Chuẩn bị dữ liệu cho Excel
    summary_data = []
    detailed_data = []
    
    for result in results:
        # Dữ liệu tổng quan
        summary_row = {
            'Tên file': result['filename'],
            'Trạng thái': result['status'],
            'Thời gian xử lý (s)': round(result['processing_time'], 2),
            'Lỗi': result.get('error', ''),
        }
        
        # Thêm điểm số nếu có
        if result.get('scores'):
            scores = result['scores']
            summary_row.update({
                'Điểm tổng': scores.get('total_score', 0),
                'Điểm học vấn': scores.get('education_score', 0),
                'Điểm kinh nghiệm': scores.get('work_experience_score', 0),
                'Điểm kỹ năng': scores.get('technical_skills_score', 0),
                'Điểm chứng chỉ': scores.get('certifications_score', 0),
                'Điểm dự án': scores.get('projects_score', 0),
                'Điểm kỹ năng mềm': scores.get('languages_and_skills_score', 0),
            })
        
        summary_data.append(summary_row)
        
        # Dữ liệu chi tiết (nếu CV được parse thành công)
        if result.get('parsed_data') and result['status'] == 'completed':
            try:
                parsed_json = json.loads(result['parsed_data'])
                detailed_row = {
                    'Tên file': result['filename'],
                    'Thông tin cá nhân': parsed_json.get('info', ''),
                    'Học vấn': parsed_json.get('education', ''),
                    'Kinh nghiệm làm việc': parsed_json.get('work_experience', ''),
                    'Kỹ năng kỹ thuật': parsed_json.get('technical_skills', ''),
                    'Chứng chỉ': parsed_json.get('certifications', ''),
                    'Dự án': parsed_json.get('projects', ''),
                    'Kỹ năng mềm': parsed_json.get('languages_and_skills', ''),
                }
                detailed_data.append(detailed_row)
            except json.JSONDecodeError:
                pass
    
    # Tạo Excel file với nhiều sheet
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        # Sheet tổng quan
        if summary_data:
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name='Tổng quan', index=False)
        
        # Sheet chi tiết
        if detailed_data:
            df_detailed = pd.DataFrame(detailed_data)
            df_detailed.to_excel(writer, sheet_name='Chi tiết CV', index=False)
        
        # Sheet yêu cầu công việc (nếu có)
        if job_requirements:
            job_df = pd.DataFrame([{'Yêu cầu công việc': job_requirements}])
            job_df.to_excel(writer, sheet_name='Yêu cầu công việc', index=False)
    
    print(f"✅ Đã export thành công: {excel_file}")
    return excel_file


def export_results_to_csv(results, output_folder="output"):
    """
    Export kết quả xử lý CV ra file CSV (đơn giản hơn Excel)
    
    Args:
        results (list): Danh sách kết quả xử lý CV
        output_folder (str): Thư mục lưu file CSV
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = os.path.join(output_folder, f"cv_analysis_results_{timestamp}.csv")
    
    print(f"📊 Đang export kết quả ra CSV: {csv_file}")
    
    # Chuẩn bị dữ liệu
    data = []
    for result in results:
        row = {
            'Tên file': result['filename'],
            'Trạng thái': result['status'],
            'Thời gian xử lý (s)': round(result['processing_time'], 2),
            'Lỗi': result.get('error', ''),
        }
        
        # Thêm điểm số nếu có
        if result.get('scores'):
            scores = result['scores']
            row.update({
                'Điểm tổng': scores.get('total_score', 0),
                'Điểm học vấn': scores.get('education_score', 0),
                'Điểm kinh nghiệm': scores.get('work_experience_score', 0),
                'Điểm kỹ năng': scores.get('technical_skills_score', 0),
                'Điểm chứng chỉ': scores.get('certifications_score', 0),
                'Điểm dự án': scores.get('projects_score', 0),
                'Điểm kỹ năng mềm': scores.get('languages_and_skills_score', 0),
            })
        
        data.append(row)
    
    # Export CSV
    df = pd.DataFrame(data)
    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    
    print(f"✅ Đã export thành công: {csv_file}")
    return csv_file


def print_batch_summary(results):
    """
    In tóm tắt kết quả xử lý batch CV
    
    Args:
        results (list): Danh sách kết quả xử lý CV
    """
    total_cvs = len(results)
    completed_cvs = len([r for r in results if r['status'] == 'completed'])
    failed_cvs = len([r for r in results if r['status'] == 'failed'])
    
    total_time = sum(r['processing_time'] for r in results)
    avg_time = total_time / total_cvs if total_cvs > 0 else 0
    
    print("\n" + "="*60)
    print("📊 TÓM TẮT KẾT QUẢ XỬ LÝ BATCH CV")
    print("="*60)
    print(f"📁 Tổng số CV: {total_cvs}")
    print(f"✅ Thành công: {completed_cvs}")
    print(f"❌ Thất bại: {failed_cvs}")
    print(f"⏱️  Tổng thời gian: {total_time:.2f} giây")
    print(f"⏱️  Thời gian trung bình: {avg_time:.2f} giây/CV")
    print(f"📈 Tỷ lệ thành công: {(completed_cvs/total_cvs*100):.1f}%")
    
    # Hiển thị CV có điểm cao nhất (nếu có scoring)
    scored_cvs = [r for r in results if r.get('scores') and r['status'] == 'completed']
    if scored_cvs:
        best_cv = max(scored_cvs, key=lambda x: x['scores'].get('total_score', 0))
        print(f"🏆 CV tốt nhất: {best_cv['filename']} (điểm: {best_cv['scores'].get('total_score', 0)})")
    
    # Hiển thị CV thất bại
    if failed_cvs > 0:
        print("\n❌ CV THẤT BẠI:")
        for result in results:
            if result['status'] == 'failed':
                print(f"   - {result['filename']}: {result.get('error', 'Lỗi không xác định')}")
    
    print("="*60)


# =============================================================================
# MAIN BATCH PROCESSING FUNCTION
# =============================================================================

def batch_process_cvs(cv_folder_path, job_requirements="", max_workers=3, output_format='excel'):
    """
    Function chính để xử lý batch nhiều CV
    
    Args:
        cv_folder_path (str): Đường dẫn thư mục chứa CV
        job_requirements (str): Yêu cầu công việc để tính điểm
        max_workers (int): Số thread tối đa
        output_format (str): Định dạng export ('excel' hoặc 'csv')
        
    Returns:
        list: Kết quả xử lý tất cả CV
    """
    print("🚀 BẮT ĐẦU BATCH PROCESSING CV")
    print("="*50)
    
    # Bước 1: Quét file CV
    cv_files = scan_cv_files(cv_folder_path)
    if not cv_files:
        print("❌ Không tìm thấy file CV nào!")
        return []
    
    # Bước 2: Xử lý batch CV
    results = process_multiple_cvs(
        cv_files=cv_files,
        job_requirements=job_requirements,
        max_workers=max_workers
    )
    
    # Bước 3: Export kết quả
    if results:
        if output_format.lower() == 'excel':
            export_results_to_excel(results, job_requirements=job_requirements)
        else:
            export_results_to_csv(results)
    
    # Bước 4: In tóm tắt
    print_batch_summary(results)
    
    return results


# =============================================================================
# DEMO FUNCTION - CÁCH SỬ DỤNG
# =============================================================================

def demo_batch_processing():
    """
    Demo function để test batch processing
    """
    print("🎯 DEMO BATCH PROCESSING CV")
    print("="*40)
    
    # Cấu hình demo
    cv_folder = input("📁 Nhập đường dẫn thư mục chứa CV: ").strip()
    
    if not cv_folder:
        cv_folder = "cv_samples"  # Thư mục mặc định
    
    job_req = input("💼 Nhập yêu cầu công việc (Enter để bỏ qua): ").strip()
    
    max_workers = input("⚡ Số thread tối đa (mặc định 3): ").strip()
    max_workers = int(max_workers) if max_workers.isdigit() else 3
    
    # Chạy batch processing
    results = batch_process_cvs(
        cv_folder_path=cv_folder,
        job_requirements=job_req,
        max_workers=max_workers,
        output_format='excel'
    )
    
    print(f"\n🎉 Hoàn thành! Đã xử lý {len(results)} CV.")
    return results


if __name__ == "__main__":
    # Uncomment dòng dưới để chạy demo
    # demo_batch_processing()
    
    # Hoặc sử dụng trực tiếp:
    # results = batch_process_cvs("path/to/cv/folder", "Software Engineer requirements", max_workers=5)
    pass