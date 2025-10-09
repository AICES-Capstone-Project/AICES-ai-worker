# 🚀 Quick Start Guide - AI Resume Score API

## ⚡ Get Started in 3 Steps

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Start the Server

```bash
python app.py
```

Server will start at `http://localhost:8000`

### Step 3: Test the API

```bash
python test_ai_score.py
```

---

## 🎯 Complete Example

### Parse a Resume First

**Upload PDF** → `POST /process`

```python
# Via web interface: Upload PDF file
# Or programmatically:
with open('resume.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/process',
        files={'pdf_doc': f}
    )
```

**Result**: Structured JSON

```json
{
	"info": "John Doe, Software Engineer, john@email.com",
	"education": "BS Computer Science, MIT, 2020",
	"work_experience": "Software Engineer at Google...",
	"technical_skills": "Python, JavaScript, React, AWS...",
	"certifications": "AWS Solutions Architect",
	"projects": "Built real-time chat app...",
	"languages_and_skills": "English, Leadership, Agile"
}
```

---

### Calculate AI Score

**Score Resume** → `POST /api/ai/score`

```python
import requests

# The parsed resume data from Step 1
parsed_resume = {
    "info": "John Doe, Software Engineer, john@email.com",
    "education": "BS Computer Science, MIT, 2020",
    "work_experience": "Software Engineer at Google (2020-2023): Developed microservices...",
    "technical_skills": "Python, JavaScript, React, Node.js, Docker, AWS",
    "certifications": "AWS Certified Solutions Architect",
    "projects": "Built real-time chat app with WebSockets and Redis",
    "languages_and_skills": "English, Spanish, Leadership, Agile"
}

# Job requirements
job_requirements = """
Senior Full-Stack Developer
- 3+ years experience
- Strong Python and JavaScript
- React, Node.js experience
- AWS cloud knowledge
- Docker/Kubernetes
- Team leadership
"""

# Call the API
response = requests.post(
    'http://localhost:8000/api/ai/score',
    json={
        'parsed_resume': parsed_resume,
        'job_requirements': job_requirements
    }
)

scores = response.json()
```

**Result**: Detailed Scores + AI Explanations

```json
{
	"education_score": 85,
	"work_experience_score": 92,
	"technical_skills_score": 88,
	"certifications_score": 75,
	"projects_score": 80,
	"languages_and_skills_score": 78,
	"total_score": 86.15,
	"AIExplanation": {
		"education": "Excellent educational background from MIT with relevant CS degree.",
		"work_experience": "Strong experience at top tech company with relevant technologies.",
		"technical_skills": "Comprehensive skill set matching all key job requirements.",
		"certifications": "Has relevant AWS certification aligned with job needs.",
		"projects": "Good project experience demonstrating practical application.",
		"languages_soft": "Strong soft skills and bilingual capabilities."
	}
}
```

**Display the Results:**

```python
print(f"🎯 Total Score: {scores['total_score']}/100")
print(f"\n📊 Breakdown:")
print(f"   Education: {scores['education_score']}/100")
print(f"   Work Experience: {scores['work_experience_score']}/100")
print(f"   Technical Skills: {scores['technical_skills_score']}/100")
print(f"   Certifications: {scores['certifications_score']}/100")
print(f"   Projects: {scores['projects_score']}/100")
print(f"   Languages & Skills: {scores['languages_and_skills_score']}/100")
```

---

## 🔥 One-Liner Tests

### Test with cURL

```bash
curl -X POST http://localhost:8000/api/ai/score \
  -H "Content-Type: application/json" \
  -d '{"parsed_resume":{"info":"John Doe","education":"BS CS","work_experience":"5 years Python","technical_skills":"Python, AWS","certifications":"AWS","projects":"Web apps","languages_and_skills":"English"},"job_requirements":"Python developer needed"}'
```

### Test with Python

```bash
python test_ai_score.py
```

### Test with JavaScript (Node.js)

```javascript
fetch("http://localhost:8000/api/ai/score", {
	method: "POST",
	headers: { "Content-Type": "application/json" },
	body: JSON.stringify({
		parsed_resume: {
			info: "Jane Smith, Developer",
			education: "BS Computer Science",
			work_experience: "3 years at startup",
			technical_skills: "Python, React, AWS",
			certifications: "None",
			projects: "E-commerce platform",
			languages_and_skills: "English, Spanish",
		},
		job_requirements: "Looking for mid-level developer with Python and React",
	}),
})
	.then((r) => r.json())
	.then((data) => console.log("Score:", data.total_score));
```

---

## 📊 Understanding Scores

| Total Score | Meaning         | Action                                       |
| ----------- | --------------- | -------------------------------------------- |
| 85-100      | Excellent Match | Strong candidate - proceed to interview      |
| 70-84       | Good Match      | Qualified candidate - consider for interview |
| 55-69       | Moderate Match  | May need additional evaluation               |
| 40-54       | Weak Match      | Likely not a good fit                        |
| 0-39        | Poor Match      | Does not meet requirements                   |

---

## 🎨 Scoring Weights

The total score is calculated as:

```
Total = (Education × 15%)
      + (Work Experience × 25%)
      + (Technical Skills × 35%)      ← Highest weight
      + (Certifications × 5%)
      + (Projects × 15%)
      + (Languages & Skills × 5%)
```

**Why these weights?**

- **Technical Skills (35%)**: Most critical for job performance
- **Work Experience (25%)**: Demonstrates practical ability
- **Education (15%)** & **Projects (15%)**: Shows foundation and initiative
- **Certifications (5%)** & **Languages (5%)**: Nice-to-have additions

---

## 🛠️ Troubleshooting

### Issue: "Connection refused"

**Solution**: Make sure Flask app is running

```bash
python app.py
```

### Issue: "No JSON data provided"

**Solution**: Include `Content-Type: application/json` header

### Issue: "Missing 'parsed_resume' field"

**Solution**: Ensure request body has `parsed_resume` key

```python
# ✅ Correct
{"parsed_resume": {...}, "job_requirements": "..."}

# ❌ Wrong
{"resume": {...}}
```

### Issue: Low scores across all categories

**Solution**:

1. Check if resume data is properly parsed
2. Ensure job requirements are detailed enough
3. Verify resume content matches job needs

---

## 📚 Additional Resources

- **API_DOCUMENTATION.md** - Complete API reference
- **IMPLEMENTATION_SUMMARY.md** - Technical details
- **test_ai_score.py** - Working example code

---

## 💡 Pro Tips

1. **More detailed job requirements = better scoring accuracy**
   - Include specific technologies, years of experience, required skills
2. **Parse resume first, then score**
   - Always use the output from `/process` as input to `/api/ai/score`
3. **Experiment with different job descriptions**
   - Same resume can score differently against different job requirements
4. **Use AI explanations to understand scores**
   - The explanations tell you _why_ a score was given

---

## 🎉 You're Ready!

The AI Resume Score API is now fully functional and ready to use. Start by running the test script to see it in action!

```bash
python test_ai_score.py
```

Happy scoring! 🚀
