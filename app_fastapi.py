# FastAPI APP - Run using: uvicorn app_fastapi:app --reload --port 8000
import os
import sys
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Optional
import json
import time
import threading
from pathlib import Path
import asyncio
from resumeparser import (
    ats_extractor, 
    ai_score_calculator, 
    extract_text_from_file,
    process_multiple_cvs_async  # New async version!
)

sys.path.insert(0, os.path.abspath(os.getcwd()))

# Paths
UPLOAD_PATH = Path("__DATA__")
BATCH_UPLOAD_PATH = Path("__DATA__/batch")
UPLOAD_PATH.mkdir(exist_ok=True)
BATCH_UPLOAD_PATH.mkdir(exist_ok=True)

# FastAPI app
app = FastAPI(
    title="Resume Parser API",
    description="AI-powered resume parser with batch processing",
    version="2.0.0"
)

# Templates
templates = Jinja2Templates(directory="templates")

# Global storage for batch processing progress
batch_progress = {
    'total': 0,
    'completed': 0,
    'current_file': '',
    'results': [],
    'status': 'idle'  # idle, processing, completed, error
}
progress_lock = threading.Lock()


# Helper function to read PDF
def _read_file_from_path(path: str) -> str:
    """Extract text from PDF file"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        data = ""
        for page_no in range(len(reader.pages)):
            page = reader.pages[page_no]
            data += page.extract_text()
        return data
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""


# ============================================================================
# ROUTES
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main page"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/process")
async def process_single_cv(
    request: Request,
    pdf_doc: UploadFile = File(...)
):
    """Process a single CV and return parsed data with scores"""
    try:
        # Save uploaded file
        file_path = UPLOAD_PATH / "file.pdf"
        with open(file_path, "wb") as f:
            content = await pdf_doc.read()
            f.write(content)
        
        # Step 1: Extract text from PDF
        resume_text = _read_file_from_path(str(file_path))
        
        # Step 2: Parse resume with ATS extractor
        data = ats_extractor(resume_text)
        
        # Try to parse JSON with error handling
        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Raw data: {data}")
            parsed_data = {
                "error": "Failed to parse resume data",
                "raw_response": data[:500] + "..." if len(data) > 500 else data
            }
            return templates.TemplateResponse(
                "index.html",
                {"request": request, "data": parsed_data, "scores": None}
            )

        # Step 3: Calculate AI score automatically
        scores = None
        try:
            # Default job requirements
            job_requirements = """
            Job Description

                Participate in developing and optimizing the user interface (UI) for websites/web applications (SPA, responsive, PWA).

                Convert mockups/UI/UX designs into high-quality, standard-compliant, high-performance, and cross-platform compatible frontend source code.

                Optimize performance, responsiveness, and user experience (UX) across various devices and browsers.

                Candidate Requirements

                Bachelor's or College degree in Information Technology, Computer Science, or a related field.

                Minimum 03 years of experience in frontend development.

                Proficient in ReactJS, NodeJS, React Native... (ReactJS is preferred).

                Experience using Git, Jira, Confluence.

                Knowledge/experience with Docker, Kubernetes is a plus.

                Good communication and teamwork skills; effective collaboration with Designers, Backend, and QA teams.

                High sense of responsibility, proactive, eager to learn, and ambitious.

                Proficient in using Vibe Coding (or similar AI coding assistant tools).
            """
            
            print("📊 Calculating AI scores...")
            scores = ai_score_calculator(parsed_data, job_requirements)
            print(f"✅ Scores calculated: Total = {scores.get('total_score', 0)}")
            
        except Exception as score_error:
            print(f"⚠️ Error calculating scores: {score_error}")
            import traceback
            traceback.print_exc()
            scores = None

        return templates.TemplateResponse(
            "index.html",
            {"request": request, "data": parsed_data, "scores": scores}
        )
        
    except Exception as e:
        print(f"Error in process route: {e}")
        import traceback
        traceback.print_exc()
        error_data = {
            "error": f"An error occurred: {str(e)}",
            "raw_response": None
        }
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "data": error_data, "scores": None}
        )


@app.post("/api/ai/score")
async def ai_score(request: Request):
    """
    API endpoint to calculate AI-based resume score.
    
    Expected JSON body:
    {
        "parsed_resume": { ... },
        "job_requirements": "string or dict"
    }
    """
    try:
        data = await request.json()
        
        if not data:
            return JSONResponse(
                content={"error": "No JSON data provided"},
                status_code=400
            )
        
        parsed_resume = data.get('parsed_resume')
        job_requirements = data.get('job_requirements', 'General software development position')
        
        if not parsed_resume:
            return JSONResponse(
                content={"error": "Missing 'parsed_resume' field in request body"},
                status_code=400
            )
        
        # Calculate scores using AI
        scores = ai_score_calculator(parsed_resume, job_requirements)
        
        return JSONResponse(content=scores, status_code=200)
        
    except Exception as e:
        print(f"Error in ai_score endpoint: {e}")
        import traceback
        traceback.print_exc()
        
        return JSONResponse(
            content={
                "error": f"An error occurred: {str(e)}",
                "education_score": 0,
                "work_experience_score": 0,
                "technical_skills_score": 0,
                "certifications_score": 0,
                "projects_score": 0,
                "languages_and_skills_score": 0,
                "total_score": 0
            },
            status_code=500
        )


# ============================================================================
# BATCH PROCESSING ENDPOINTS
# ============================================================================

@app.post("/batch_process")
async def batch_process(
    pdf_docs: List[UploadFile] = File(...),
    job_requirements: Optional[str] = Form("")
):
    """Handle batch processing of multiple CVs"""
    try:
        if not pdf_docs or len(pdf_docs) == 0:
            return JSONResponse(
                content={'error': 'No files uploaded'},
                status_code=400
            )
        
        # Reset progress
        with progress_lock:
            batch_progress['total'] = len(pdf_docs)
            batch_progress['completed'] = 0
            batch_progress['current_file'] = ''
            batch_progress['results'] = []
            batch_progress['status'] = 'processing'
        
        # Save files and get paths
        file_paths = []
        for idx, file in enumerate(pdf_docs):
            if file.filename:
                filename = f"batch_{idx}_{file.filename}"
                filepath = BATCH_UPLOAD_PATH / filename
                
                # Save file
                with open(filepath, "wb") as f:
                    content = await file.read()
                    f.write(content)
                
                file_paths.append((str(filepath), file.filename))
        
        # Start background processing
        thread = threading.Thread(
            target=process_batch_cvs_background,
            args=(file_paths, job_requirements)
        )
        thread.daemon = True
        thread.start()
        
        return JSONResponse(
            content={
                'message': 'Batch processing started',
                'total_files': len(pdf_docs)
            },
            status_code=200
        )
        
    except Exception as e:
        print(f"Error in batch_process: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={'error': str(e)},
            status_code=500
        )


async def process_batch_cvs_background_async(file_paths, job_requirements):
    """
    ASYNC Background task to process multiple CVs
    Using asyncio for better performance!
    """
    try:
        # Extract just file paths for async processing
        cv_files = [fp for fp, _ in file_paths]
        
        # Process with async version
        results = await process_multiple_cvs_async(
            cv_files=cv_files,
            job_requirements=job_requirements,
            max_concurrent=20  # Process 20 CVs concurrently!
        )
        
        # Update progress with results
        with progress_lock:
            batch_progress['results'] = results
            batch_progress['completed'] = len(results)
            batch_progress['status'] = 'completed'
            batch_progress['current_file'] = ''
        
    except Exception as e:
        print(f"Error in async background processing: {e}")
        import traceback
        traceback.print_exc()
        with progress_lock:
            batch_progress['status'] = 'error'


def process_batch_cvs_background(file_paths, job_requirements):
    """
    Background task wrapper - runs async processing in new event loop
    """
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run async processing
        loop.run_until_complete(
            process_batch_cvs_background_async(file_paths, job_requirements)
        )
        
        loop.close()
        
    except Exception as e:
        print(f"Error in background processing: {e}")
        import traceback
        traceback.print_exc()
        with progress_lock:
            batch_progress['status'] = 'error'


@app.get("/batch_progress")
async def batch_progress_stream(request: Request):
    """Server-Sent Events endpoint for real-time progress updates"""
    async def generate():
        last_completed = -1
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break
            
            with progress_lock:
                current_completed = batch_progress['completed']
                total = batch_progress['total']
                current_file = batch_progress['current_file']
                status = batch_progress['status']
                
                # Only send update if something changed
                if current_completed != last_completed or status == 'completed':
                    percentage = (current_completed / total * 100) if total > 0 else 0
                    
                    data = {
                        'completed': current_completed,
                        'total': total,
                        'percentage': round(percentage, 1),
                        'current_file': current_file,
                        'status': status
                    }
                    
                    yield f"data: {json.dumps(data)}\n\n"
                    last_completed = current_completed
                    
                    # Stop streaming when completed
                    if status in ['completed', 'error']:
                        break
            
            await asyncio.sleep(0.5)  # Update every 500ms
    
    return StreamingResponse(
        generate(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


@app.get("/batch_results")
async def batch_results():
    """Get the results of batch processing"""
    with progress_lock:
        return JSONResponse(content={
            'status': batch_progress['status'],
            'total': batch_progress['total'],
            'completed': batch_progress['completed'],
            'results': batch_progress['results']
        })


# ============================================================================
# STARTUP
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app_fastapi:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

