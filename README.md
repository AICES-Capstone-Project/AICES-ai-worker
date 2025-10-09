# Resume Parser App (Gen AI + Flask)

### Objective

Creating a resume parser app using Flask is a great way to help job seekers test the ATS (Applicant Tracking System) friendliness of their resumes. The app allows users to upload their resumes in PDF format, which are then parsed to extract various pieces of information such as full name, email ID, GitHub portfolio, LinkedIn ID, employment details, technical skills, and soft skills. The extracted information is then presented in JSON format, providing users with valuable insights into the effectiveness of their resumes.

To build such an app, you can leverage various tools and libraries, including Python, Flask, Pyresparser, pdfminer.six, docx2txt, and NLP (natural language processing) libraries such as nltk and spacy. These tools enable the extraction of essential information from resumes in PDF and DOCx formats, making the process automated and efficient.

The app's functionality aligns with the growing need for streamlined recruitment processes and the increasing reliance on technology to evaluate and process job applications. By providing users with a detailed analysis of their resumes, the app empowers job seekers to optimize their resumes for better visibility and compatibility with ATS.

### Sneak Peak of the App

![image](https://github.com/pik1989/Resume-Parser-OpenAI/assets/34673684/5d206207-1b25-4dbe-8e11-add701b632e7)

#### Overview:

This App is created for job seekers to test whether their resumes are ATS friendly or not, if our App is able to parse your details and show it, then assume that everything is good.

#### Features:

- **Resume Parsing**: Extract specific information from resumes including personal info, education, work experience, skills, certifications, and projects
- **JSON Output**: Present extracted data in structured JSON format for easy integration
- **AI-Powered Scoring**: NEW! Calculate intelligent resume scores against job requirements using Google Gemini AI
- **Weighted Evaluation**: Get detailed scores for each resume section with AI explanations
- **RESTful API**: Easy-to-use API endpoints for both parsing and scoring

#### Installation:

Run the pip install requirements.txt to install and set up the app, including any dependencies and prerequisites.

#### Usage:

**Web Interface:**
Just upload your resume in pdf format, and see for yourself :)

**API Endpoints:**

1. **POST `/process`** - Upload and parse PDF resume

   - Upload: PDF file via form-data
   - Returns: Structured JSON with resume data

2. **POST `/api/ai/score`** - Calculate AI resume score (NEW!)

   - Input: Parsed resume JSON + job requirements
   - Returns: Weighted scores (0-100) for each section + AI explanations

   Example:

   ```json
   {
     "parsed_resume": { ... },
     "job_requirements": "Senior Developer with 3+ years Python..."
   }
   ```

   See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for detailed usage examples.

##### Running the program

1. Clone the repository to your local machine
2. Navigate to the project directory
3. Install all the required libraries:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure your API key in `config.yaml`:
   ```yaml
   GEMINI_API_KEY: "your-api-key-here"
   ```
5. Run the Flask application:
   ```bash
   python app.py
   ```
6. Open your browser and go to:
   ```
   http://localhost:8000
   ```

##### Testing the AI Score API

Run the included test script to see the AI scoring in action:

```bash
python test_ai_score.py
```

Overall, the development of a resume parser app using Flask represents a significant advancement in leveraging technology to support job seekers in optimizing their resumes for the modern recruitment landscape. This app aligns with the increasing demand for efficient and technology-driven solutions in the job application process, ultimately benefiting both job seekers and recruiters.
