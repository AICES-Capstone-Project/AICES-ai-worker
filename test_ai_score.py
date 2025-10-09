"""
Test script for the AI Score API endpoint
Run this after starting the Flask app (python app.py)
"""

import requests
import json

# API endpoint
url = "http://localhost:8000/api/ai/score"

# Example parsed resume data (what you get from ats_extractor)
parsed_resume = {
    "info": "John Doe, Software Engineer, john.doe@email.com, +1234567890",
    "education": "Bachelor of Science in Computer Science, MIT, 2020. GPA: 3.8/4.0",
    "work_experience": "Software Engineer at Google (2020-2023): Developed scalable microservices using Python and Go. Led a team of 5 engineers. Improved API performance by 40%.",
    "technical_skills": "Python, JavaScript, React, Node.js, Docker, Kubernetes, AWS, PostgreSQL, MongoDB, Git",
    "certifications": "AWS Certified Solutions Architect, Google Cloud Professional",
    "projects": "Built a real-time chat application using WebSockets and Redis. Developed an ML model for image classification with 95% accuracy.",
    "languages_and_skills": "English (Native), Spanish (Intermediate), Leadership, Team Collaboration, Agile methodology"
}

# Job requirements
job_requirements = """
Senior Full-Stack Developer Position:

Requirements:
- 3+ years of experience in web development
- Strong proficiency in Python and JavaScript
- Experience with React, Node.js, and modern frameworks
- Knowledge of cloud platforms (AWS, GCP, or Azure)
- Experience with Docker and Kubernetes
- Strong problem-solving and communication skills
- Bachelor's degree in Computer Science or related field
- Experience leading small teams is a plus

Preferred:
- AWS or cloud certifications
- Experience with microservices architecture
- Machine learning knowledge
"""

# Request payload
payload = {
    "parsed_resume": parsed_resume,
    "job_requirements": job_requirements
}

# Make the API call
try:
    print("🚀 Sending request to AI Score API...\n")
    response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
    
    if response.status_code == 200:
        scores = response.json()
        
        print("✅ SUCCESS! AI Score Results:")
        print("=" * 60)
        print(f"📊 Education Score: {scores.get('education_score')}/100")
        print(f"💼 Work Experience Score: {scores.get('work_experience_score')}/100")
        print(f"💻 Technical Skills Score: {scores.get('technical_skills_score')}/100")
        print(f"🏆 Certifications Score: {scores.get('certifications_score')}/100")
        print(f"🔧 Projects Score: {scores.get('projects_score')}/100")
        print(f"🗣️  Languages & Skills Score: {scores.get('languages_and_skills_score')}/100")
        print("=" * 60)
        print(f"🎯 TOTAL WEIGHTED SCORE: {scores.get('total_score')}/100")
        print("=" * 60)
        
        if 'AIExplanation' in scores:
            print("\n📝 AI Explanations:")
            print("-" * 60)
            explanations = scores['AIExplanation']
            print(f"\n📚 Education: {explanations.get('education')}")
            print(f"\n💼 Work Experience: {explanations.get('work_experience')}")
            print(f"\n💻 Technical Skills: {explanations.get('technical_skills')}")
            print(f"\n🏆 Certifications: {explanations.get('certifications')}")
            print(f"\n🔧 Projects: {explanations.get('projects')}")
            print(f"\n🗣️  Languages & Soft Skills: {explanations.get('languages_soft')}")
        
        print("\n" + "=" * 60)
        print("\n📄 Full JSON Response:")
        print(json.dumps(scores, indent=2))
        
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.json())
        
except requests.exceptions.ConnectionError:
    print("❌ Error: Cannot connect to the server.")
    print("Make sure the Flask app is running on http://localhost:8000")
    print("Run: python app.py")
    
except Exception as e:
    print(f"❌ Unexpected error: {e}")

