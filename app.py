# FLASK APP - Run the app using flask --app app.py run
import os, sys
from flask import Flask, request, render_template, jsonify
from pypdf import PdfReader 
import json
from resumeparser import ats_extractor, ai_score_calculator

sys.path.insert(0, os.path.abspath(os.getcwd()))


UPLOAD_PATH = r"__DATA__"
app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')

@app.route("/process", methods=["POST"])
def ats():
    try:
        doc = request.files['pdf_doc']
        doc.save(os.path.join(UPLOAD_PATH, "file.pdf"))
        doc_path = os.path.join(UPLOAD_PATH, "file.pdf")
        data = _read_file_from_path(doc_path)
        data = ats_extractor(data)
        
        # Try to parse JSON with error handling
        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Raw data: {data}")
            # Return error message to user
            parsed_data = {
                "error": "Failed to parse resume data",
                "raw_response": data[:500] + "..." if len(data) > 500 else data
            }

        return render_template('index.html', data = parsed_data)
        
    except Exception as e:
        print(f"Error in ats route: {e}")
        error_data = {
            "error": f"An error occurred: {str(e)}",
            "raw_response": None
        }
        return render_template('index.html', data = error_data)
 
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


if __name__ == "__main__":
    app.run(port=8000, debug=True)

