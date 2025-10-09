# AI Resume Score API Documentation

## Overview

The AI Resume Score API endpoint provides intelligent scoring of resumes against job requirements using Google's Gemini AI model.

## Endpoint

### POST `/api/ai/score`

Calculates an AI-based resume score by comparing parsed resume data with job requirements.

---

## Request

### Headers

```
Content-Type: application/json
```

### Body Parameters

| Parameter          | Type          | Required | Description                                                                           |
| ------------------ | ------------- | -------- | ------------------------------------------------------------------------------------- |
| `parsed_resume`    | Object        | Yes      | The structured resume data (output from `ats_extractor`)                              |
| `job_requirements` | String/Object | No       | Job description or requirements (defaults to "General software development position") |

### Example Request Body

```json
{
	"parsed_resume": {
		"info": "John Doe, Software Engineer, john.doe@email.com, +1234567890",
		"education": "Bachelor of Science in Computer Science, MIT, 2020. GPA: 3.8/4.0",
		"work_experience": "Software Engineer at Google (2020-2023): Developed scalable microservices...",
		"technical_skills": "Python, JavaScript, React, Node.js, Docker, Kubernetes, AWS...",
		"certifications": "AWS Certified Solutions Architect, Google Cloud Professional",
		"projects": "Built a real-time chat application using WebSockets...",
		"languages_and_skills": "English (Native), Spanish (Intermediate), Leadership..."
	},
	"job_requirements": "Senior Full-Stack Developer Position: 3+ years experience, Python, JavaScript, React..."
}
```

---

## Response

### Success Response (200 OK)

```json
{
	"education_score": 80,
	"work_experience_score": 90,
	"technical_skills_score": 85,
	"certifications_score": 60,
	"projects_score": 70,
	"languages_and_skills_score": 75,
	"total_score": 81.75,
	"AIExplanation": {
		"education": "Strong educational background from a top-tier university with relevant degree in Computer Science.",
		"work_experience": "Excellent work experience at a major tech company with demonstrated leadership and technical achievements.",
		"technical_skills": "Comprehensive skill set matching most job requirements including cloud platforms and modern frameworks.",
		"certifications": "Has relevant cloud certifications which align well with the position requirements.",
		"projects": "Good project portfolio demonstrating practical application of skills in real-world scenarios.",
		"languages_soft": "Strong soft skills and bilingual capabilities, though could benefit from more specific agile experience."
	}
}
```

### Error Response (400 Bad Request)

```json
{
	"error": "Missing 'parsed_resume' field in request body"
}
```

### Error Response (500 Internal Server Error)

```json
{
	"error": "An error occurred: ...",
	"education_score": 0,
	"work_experience_score": 0,
	"technical_skills_score": 0,
	"certifications_score": 0,
	"projects_score": 0,
	"languages_and_skills_score": 0,
	"total_score": 0
}
```

---

## Scoring System

### Individual Scores (0-100)

Each category is scored on a scale of 0 to 100:

- **0-40**: Poor/Insufficient
- **41-60**: Below average/Needs improvement
- **61-75**: Average/Adequate
- **76-85**: Good/Strong
- **86-100**: Excellent/Outstanding

### Weighted Total Score

The total score is calculated using the following weights:

| Category           | Weight |
| ------------------ | ------ |
| Education          | 15%    |
| Work Experience    | 25%    |
| Technical Skills   | 35%    |
| Certifications     | 5%     |
| Projects           | 15%    |
| Languages & Skills | 5%     |

**Formula:**

```
total_score =
  (education_score × 0.15) +
  (work_experience_score × 0.25) +
  (technical_skills_score × 0.35) +
  (certifications_score × 0.05) +
  (projects_score × 0.15) +
  (languages_and_skills_score × 0.05)
```

---

## Usage Examples

### Python (requests)

```python
import requests

url = "http://localhost:8000/api/ai/score"

payload = {
    "parsed_resume": {
        "info": "Jane Smith, Full-Stack Developer...",
        "education": "BS in Computer Science, Stanford...",
        "work_experience": "5 years at tech startups...",
        "technical_skills": "Python, React, AWS...",
        "certifications": "AWS Solutions Architect...",
        "projects": "E-commerce platform...",
        "languages_and_skills": "English, Spanish, Agile..."
    },
    "job_requirements": "Looking for a senior developer with 3+ years experience..."
}

response = requests.post(url, json=payload)
scores = response.json()

print(f"Total Score: {scores['total_score']}")
```

### JavaScript (fetch)

```javascript
const url = "http://localhost:8000/api/ai/score";

const payload = {
	parsed_resume: {
		info: "Jane Smith, Full-Stack Developer...",
		education: "BS in Computer Science...",
		// ... other fields
	},
	job_requirements: "Looking for a senior developer...",
};

fetch(url, {
	method: "POST",
	headers: {
		"Content-Type": "application/json",
	},
	body: JSON.stringify(payload),
})
	.then((response) => response.json())
	.then((data) => {
		console.log("Total Score:", data.total_score);
		console.log("Explanations:", data.AIExplanation);
	});
```

### cURL

```bash
curl -X POST http://localhost:8000/api/ai/score \
  -H "Content-Type: application/json" \
  -d '{
    "parsed_resume": {
      "info": "John Doe...",
      "education": "BS Computer Science...",
      "work_experience": "Software Engineer...",
      "technical_skills": "Python, JavaScript...",
      "certifications": "AWS Certified...",
      "projects": "Web applications...",
      "languages_and_skills": "English, Leadership..."
    },
    "job_requirements": "Senior developer position requiring 3+ years..."
  }'
```

---

## Integration Workflow

### Complete Resume Evaluation Flow

```python
# Step 1: Extract resume text from PDF
from pypdf import PdfReader

reader = PdfReader("resume.pdf")
resume_text = ""
for page in reader.pages:
    resume_text += page.extract_text()

# Step 2: Parse resume using ATS extractor
from resumeparser import ats_extractor
import json

parsed_data = ats_extractor(resume_text)
parsed_resume = json.loads(parsed_data)

# Step 3: Calculate AI score
import requests

job_description = """
Senior Backend Engineer
- 5+ years Python experience
- AWS cloud expertise
- Microservices architecture
"""

response = requests.post(
    "http://localhost:8000/api/ai/score",
    json={
        "parsed_resume": parsed_resume,
        "job_requirements": job_description
    }
)

scores = response.json()
print(f"Candidate Score: {scores['total_score']}/100")
```

---

## Notes

- The AI model (Gemini) provides objective scoring based on the comparison between resume content and job requirements
- More detailed job requirements lead to more accurate scoring
- The API handles errors gracefully and returns detailed error messages
- All scores are rounded to 2 decimal places
- AI explanations provide context for each score to help understand the evaluation

---

## Testing

Run the included test script:

```bash
# Make sure Flask app is running
python app.py

# In another terminal, run the test
python test_ai_score.py
```

This will demonstrate the API with sample data and display formatted results.
