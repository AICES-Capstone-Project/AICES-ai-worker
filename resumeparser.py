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
                print(f"✅ SUCCESS using .parts: Extracted {len(data)} characters")
                print(f"📄 First 200 chars: {data[:200]}...")
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
                    print(f"📄 First 200 chars: {data[:200]}...")
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
        
        print(f"Raw response: {data}")  # Debug print
        
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
                temperature=0.3,  # Slightly higher for more varied scoring
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