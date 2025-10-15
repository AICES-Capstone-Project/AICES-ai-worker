# FLASK APP - Run the app using flask --app app.py run
import os, sys
from flask import Flask, request, render_template, jsonify, Response, stream_with_context
from pypdf import PdfReader 
import json
import time
import threading
from queue import Queue
from resumeparser import ats_extractor, ai_score_calculator, extract_text_from_file

sys.path.insert(0, os.path.abspath(os.getcwd()))


UPLOAD_PATH = r"__DATA__"
BATCH_UPLOAD_PATH = r"__DATA__/batch"
app = Flask(__name__)

# Global storage for batch processing progress
batch_progress = {
    'total': 0,
    'completed': 0,
    'current_file': '',
    'results': [],
    'status': 'idle'  # idle, processing, completed, error
}
progress_lock = threading.Lock()


@app.route('/')
def index():
    return render_template('index.html')

@app.route("/process", methods=["POST"])
def ats():
    try:
        doc = request.files['pdf_doc']
        doc.save(os.path.join(UPLOAD_PATH, "file.pdf"))
        doc_path = os.path.join(UPLOAD_PATH, "file.pdf")
        
        # Step 1: Extract text from PDF
        resume_text = _read_file_from_path(doc_path)
        
        # Step 2: Parse resume with ATS extractor
        data = ats_extractor(resume_text)
        
        # Try to parse JSON with error handling
        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            # print(f"Raw data: {data}")
            # Return error message to user
            parsed_data = {
                "error": "Failed to parse resume data",
                "raw_response": data[:500] + "..." if len(data) > 500 else data
            }
            return render_template('index.html', data=parsed_data, scores=None)

        # Step 3: Calculate AI score automatically
        scores = None
        try:
            # Default job requirements (can be customized later)
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
            # Continue even if scoring fails
            scores = None

        return render_template('index.html', data=parsed_data, scores=scores)
        
    except Exception as e:
        print(f"Error in ats route: {e}")
        import traceback
        traceback.print_exc()
        error_data = {
            "error": f"An error occurred: {str(e)}",
            "raw_response": None
        }
        return render_template('index.html', data=error_data, scores=None)
 
def _read_file_from_path(path):
    reader = PdfReader(path) 
    data = ""

    for page_no in range(len(reader.pages)):
        page = reader.pages[page_no] 
        data += page.extract_text()

    return data 


@app.route("/api/ai/score", methods=["POST"])
def ai_score():
    """
    API endpoint to calculate AI-based resume score.
    
    Expected JSON body:
    {
        "parsed_resume": { ... },  # The output from ats_extractor
        "job_requirements": "string or dict"  # Job description/requirements
    }
    
    Returns:
    {
        "education_score": number,
        "work_experience_score": number,
        "technical_skills_score": number,
        "certifications_score": number,
        "projects_score": number,
        "languages_and_skills_score": number,
        "total_score": number,
        "AIExplanation": { ... }
    }
    """
    try:
        # Get JSON data from request
        data = request.get_json()
        
        if not data:
            return jsonify({
                "error": "No JSON data provided"
            }), 400
        
        # Extract parsed resume and job requirements
        parsed_resume = data.get('parsed_resume')
        job_requirements = data.get('job_requirements', 'General software development position')
        
        if not parsed_resume:
            return jsonify({
                "error": "Missing 'parsed_resume' field in request body"
            }), 400
        
        # Calculate scores using AI
        scores = ai_score_calculator(parsed_resume, job_requirements)
        
        # Return the scores as JSON
        return jsonify(scores), 200
        
    except Exception as e:
        print(f"Error in ai_score endpoint: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "error": f"An error occurred: {str(e)}",
            "education_score": 0,
            "work_experience_score": 0,
            "technical_skills_score": 0,
            "certifications_score": 0,
            "projects_score": 0,
            "languages_and_skills_score": 0,
            "total_score": 0
        }), 500


@app.route("/batch_process", methods=["POST"])
def batch_process():
    """Handle batch processing of multiple CVs"""
    try:
        # Create batch upload directory if not exists
        if not os.path.exists(BATCH_UPLOAD_PATH):
            os.makedirs(BATCH_UPLOAD_PATH)
        
        # Get uploaded files
        files = request.files.getlist('pdf_docs')
        
        if not files or len(files) == 0:
            return jsonify({'error': 'No files uploaded'}), 400
        
        # Get job requirements (optional)
        job_requirements = request.form.get('job_requirements', '')
        
        # Reset progress
        with progress_lock:
            batch_progress['total'] = len(files)
            batch_progress['completed'] = 0
            batch_progress['current_file'] = ''
            batch_progress['results'] = []
            batch_progress['status'] = 'processing'
        
        # Save files and get paths
        file_paths = []
        for idx, file in enumerate(files):
            if file.filename:
                filename = f"batch_{idx}_{file.filename}"
                filepath = os.path.join(BATCH_UPLOAD_PATH, filename)
                file.save(filepath)
                file_paths.append((filepath, file.filename))
        
        # Start background processing
        thread = threading.Thread(
            target=process_batch_cvs_background,
            args=(file_paths, job_requirements)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'message': 'Batch processing started',
            'total_files': len(files)
        }), 200
        
    except Exception as e:
        print(f"Error in batch_process: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def process_batch_cvs_background(file_paths, job_requirements):
    """Background task to process multiple CVs"""
    try:
        for idx, (filepath, original_filename) in enumerate(file_paths):
            # Update current file
            with progress_lock:
                batch_progress['current_file'] = original_filename
            
            try:
                # Extract text from file
                resume_text = extract_text_from_file(filepath)
                
                if not resume_text:
                    result = {
                        'filename': original_filename,
                        'status': 'failed',
                        'error': 'Could not extract text from file',
                        'parsed_data': None,
                        'scores': None
                    }
                else:
                    # Parse resume
                    parsed_data_str = ats_extractor(resume_text)
                    
                    try:
                        parsed_data = json.loads(parsed_data_str)
                    except json.JSONDecodeError:
                        parsed_data = {'raw': parsed_data_str}
                    
                    # Calculate scores if job requirements provided
                    scores = None
                    if job_requirements:
                        try:
                            scores = ai_score_calculator(parsed_data, job_requirements)
                        except Exception as score_error:
                            print(f"Error calculating scores for {original_filename}: {score_error}")
                    
                    result = {
                        'filename': original_filename,
                        'status': 'completed',
                        'error': None,
                        'parsed_data': parsed_data,
                        'scores': scores
                    }
                
                # Add result to progress
                with progress_lock:
                    batch_progress['results'].append(result)
                    batch_progress['completed'] += 1
                
            except Exception as file_error:
                print(f"Error processing {original_filename}: {file_error}")
                result = {
                    'filename': original_filename,
                    'status': 'failed',
                    'error': str(file_error),
                    'parsed_data': None,
                    'scores': None
                }
                with progress_lock:
                    batch_progress['results'].append(result)
                    batch_progress['completed'] += 1
        
        # Mark as completed
        with progress_lock:
            batch_progress['status'] = 'completed'
            batch_progress['current_file'] = ''
        
    except Exception as e:
        print(f"Error in background processing: {e}")
        import traceback
        traceback.print_exc()
        with progress_lock:
            batch_progress['status'] = 'error'


@app.route("/batch_progress")
def batch_progress_stream():
    """Server-Sent Events endpoint for real-time progress updates"""
    def generate():
        last_completed = -1
        while True:
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
            
            time.sleep(0.5)  # Update every 500ms
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route("/batch_results")
def batch_results():
    """Get the results of batch processing"""
    with progress_lock:
        return jsonify({
            'status': batch_progress['status'],
            'total': batch_progress['total'],
            'completed': batch_progress['completed'],
            'results': batch_progress['results']
        })


if __name__ == "__main__":
    app.run(port=8000, debug=True)

