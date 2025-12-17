"""AI-powered candidate comparison service."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def compare_candidates(
    job_data: Dict[str, Any],
    api_key: str | None = None
) -> Dict[str, Any]:
    """
    Compare multiple candidates and generate detailed analysis with rankings.

    Args:
        job_data: Job data with candidates list from Redis queue
        api_key: Gemini API key for AI processing

    Returns:
        Dict with status, candidates analysis, and rankings
    """
    try:
        from worker.services.gemini_client import get_model
        import google.generativeai as genai

        # Validate input
        candidates = job_data.get("candidates", [])
        if len(candidates) < 2:
            return {
                "status": "error",
                "error": "insufficient_candidates",
                "reason": f"Not enough candidates for comparison (minimum 2 required, got {len(candidates)})"
            }

        if len(candidates) > 5:
            return {
                "status": "error",
                "error": "invalid_data",
                "reason": f"Too many candidates for comparison (maximum 5 allowed, got {len(candidates)})"
            }

        # Extract job context
        job_title = job_data.get("jobTitle", "")
        requirements = job_data.get("requirements", "")
        skills = job_data.get("skills", "")
        level = job_data.get("level", "")
        specialization = job_data.get("specialization", "")
        criteria_list = job_data.get("criteria", [])

        # Build criteria text
        criteria_text = ""
        if criteria_list:
            criteria_lines = []
            for c in criteria_list:
                name = c.get("name", "")
                weight = c.get("weight", 0)
                criteria_lines.append(f"  - {name}: {weight * 100}%")
            criteria_text = "\n".join(criteria_lines)

        # Build candidates summary for prompt
        candidates_summary = []
        for idx, candidate in enumerate(candidates, 1):
            app_id = candidate.get("applicationId")
            parsed_data = candidate.get("parsedData", {})
            match_skills = candidate.get("matchSkills", "")
            missing_skills = candidate.get("missingSkills", "")
            total_score = candidate.get("totalScore", 0)

            # Extract key info from parsed data
            name = ""
            summary = ""
            experience = []
            education = []
            skills_list = []

            if isinstance(parsed_data, dict):
                info = parsed_data.get("info", {})
                if isinstance(info, dict):
                    name = info.get("fullName") or info.get(
                        "name") or f"Candidate {idx}"

                summary = parsed_data.get("summary", "")

                work_exp = parsed_data.get("work_experience", [])
                if isinstance(work_exp, list):
                    for exp in work_exp[:3]:  # Top 3 experiences
                        if isinstance(exp, dict):
                            exp_title = exp.get("title", "")
                            exp_company = exp.get("company", "")
                            exp_duration = exp.get("duration", "")
                            experience.append(
                                f"{exp_title} at {exp_company} ({exp_duration})")

                edu = parsed_data.get("education", [])
                if isinstance(edu, list):
                    for e in edu[:2]:  # Top 2 education
                        if isinstance(e, dict):
                            degree = e.get("degree", "")
                            school = e.get("school", "")
                            education.append(f"{degree} - {school}")

                tech_skills = parsed_data.get("technical_skills", {})
                if isinstance(tech_skills, dict):
                    for skill_category, skill_items in tech_skills.items():
                        if isinstance(skill_items, list):
                            skills_list.extend(skill_items[:5])

            candidate_text = f"""
Candidate #{idx} (ApplicationId: {app_id})
Name: {name}
Total Score: {total_score:.1f}/100

Summary: {summary[:200] if summary else "Not available"}

Work Experience:
{chr(10).join(f"  - {exp}" for exp in experience[:3]) if experience else "  - Not available"}

Education:
{chr(10).join(f"  - {edu}" for edu in education[:2]) if education else "  - Not available"}

Skills:
  Matched: {match_skills if match_skills else "Not available"}
  Missing: {missing_skills if missing_skills else "Not available"}
  Technical: {", ".join(skills_list[:10]) if skills_list else "Not available"}
"""
            candidates_summary.append(candidate_text)

        candidates_text = "\n\n".join(candidates_summary)

        # Build dynamic analysis requirements from criteria
        analysis_requirements = []
        analysis_requirements.append(
            "1. **overallSummary**: Overall summary of the candidate (2-3 sentences)")
        analysis_requirements.append(
            "2. **jobFit**: Assessment of fit for this position (2-3 sentences)")

        # Add criteria-based fields
        for idx, criterion in enumerate(criteria_list, start=3):
            criteria_name = criterion.get("name", "")
            if criteria_name:
                analysis_requirements.append(
                    f"{idx}. **{criteria_name}**: Detailed analysis of candidate's {criteria_name} (2-4 sentences)")

        # Add recommendation
        analysis_requirements.append(
            f"{len(analysis_requirements) + 1}. **recommendation**: ")
        analysis_requirements.append(
            "   - rank: Ranking (1 = best, must be unique)")
        analysis_requirements.append(
            "   - reason: Reason for this ranking (2-3 sentences)")

        analysis_requirements_text = "\n".join(analysis_requirements)

        # Build JSON structure example dynamically
        analysis_fields_example = []
        analysis_fields_example.append('        "overallSummary": "...",')
        analysis_fields_example.append('        "jobFit": "...",')

        for criterion in criteria_list:
            criteria_name = criterion.get("name", "")
            if criteria_name:
                analysis_fields_example.append(
                    f'        "{criteria_name}": "...",')

        analysis_fields_example.append('        "recommendation": {')
        analysis_fields_example.append('          "rank": 1,')
        analysis_fields_example.append('          "reason": "..."')
        analysis_fields_example.append('        }')

        analysis_fields_example_text = "\n".join(analysis_fields_example)

        # Build AI prompt
        prompt = f"""You are a recruitment expert and candidate analyst. Your task is to compare {len(candidates)} candidates for the following job position and provide detailed analysis with rankings.

# JOB INFORMATION

Position: {job_title}
Level: {level}
Specialization: {specialization}
Required Skills: {skills}

Job Requirements:
{requirements[:3000]}

Evaluation Criteria (with weights):
{criteria_text}

# CANDIDATE INFORMATION

{candidates_text}

# ANALYSIS REQUIREMENTS

Analyze each candidate based on:

{analysis_requirements_text}

# FORMAT REQUIREMENTS

Return the result as JSON with the following structure (DO NOT include ```json):

{{
  "status": "success",
  "candidates": [
    {{
      "applicationId": <id>,
      "analysis": {{
{analysis_fields_example_text}
      }}
    }}
  ]
}}

# IMPORTANT NOTES

- Rankings must be unique (1, 2, 3, 4, 5...) based on job fit
- Analysis must be specific, based on actual candidate data
- Clearly explain why this candidate ranks higher/lower than others
- Use natural, professional English language for ALL analysis text
- If information is missing for any criteria, still include that field with appropriate content (e.g., "No information available about...")
- RETURN ONLY JSON, NO ADDITIONAL EXPLANATORY TEXT OUTSIDE JSON
- All analysis content (overallSummary, jobFit, criteria fields, recommendation reason) MUST be written in English
"""

        # Call AI model
        model = get_model(api_key=api_key)

        logger.info(
            "Sending comparison request to AI for %d candidates", len(candidates))

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=8192,
            ),
        )

        # Extract response text
        raw_text = ""
        if hasattr(response, "parts") and response.parts:
            raw_text = "".join(part.text for part in response.parts if getattr(
                part, "text", "")).strip()
        elif response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                raw_text = "".join(part.text for part in candidate.content.parts if getattr(
                    part, "text", "")).strip()

        if not raw_text:
            logger.error("AI returned empty response for comparison")
            return {
                "status": "error",
                "error": "processing_failed",
                "reason": "AI returned empty response"
            }

        # Clean JSON response
        cleaned = raw_text.strip()

        # Remove markdown code blocks if present
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        cleaned = cleaned.strip()

        # Parse JSON
        try:
            result = json.loads(cleaned)

            # Validate response structure
            if not isinstance(result, dict):
                raise ValueError("Response is not a dictionary")

            if "candidates" not in result:
                raise ValueError("Response missing 'candidates' field")

            if not isinstance(result["candidates"], list):
                raise ValueError("'candidates' is not a list")

            # Ensure status field
            if "status" not in result:
                result["status"] = "success"

            # Add job context to result
            result["campaignId"] = job_data.get("campaignId")
            result["jobId"] = job_data.get("jobId")

            # Build required fields list dynamically from criteria
            required_analysis_fields = ["overallSummary", "jobFit"]
            for criterion in criteria_list:
                criteria_name = criterion.get("name", "")
                if criteria_name:
                    required_analysis_fields.append(criteria_name)
            required_analysis_fields.append("recommendation")

            # Validate each candidate has required fields
            for candidate_result in result["candidates"]:
                if "applicationId" not in candidate_result:
                    raise ValueError("Candidate missing 'applicationId'")

                if "analysis" not in candidate_result:
                    raise ValueError("Candidate missing 'analysis'")

                analysis = candidate_result["analysis"]

                for field in required_analysis_fields:
                    if field not in analysis:
                        logger.warning(
                            f"Candidate {candidate_result['applicationId']} missing '{field}', adding default")
                        if field == "recommendation":
                            analysis[field] = {
                                "rank": 999, "reason": "Missing ranking information"}
                        else:
                            analysis[field] = f"No information available about {field}"

            # Validate unique ranks
            ranks = [c["analysis"]["recommendation"]["rank"]
                     for c in result["candidates"]]
            if len(ranks) != len(set(ranks)):
                logger.warning("Duplicate ranks detected, reassigning...")
                # Sort by rank and reassign
                sorted_candidates = sorted(result["candidates"],
                                           key=lambda x: x["analysis"]["recommendation"]["rank"])
                for idx, c in enumerate(sorted_candidates, 1):
                    c["analysis"]["recommendation"]["rank"] = idx

            logger.info("Successfully processed comparison for %d candidates", len(
                result["candidates"]))
            return result

        except json.JSONDecodeError as exc:
            logger.error("Failed to parse AI response as JSON: %s", exc)
            logger.error("Raw response (first 500 chars): %s", cleaned[:500])
            return {
                "status": "error",
                "error": "processing_failed",
                "reason": f"Failed to parse AI response: {str(exc)}"
            }
        except ValueError as exc:
            logger.error("Invalid response structure: %s", exc)
            return {
                "status": "error",
                "error": "processing_failed",
                "reason": f"Invalid response structure: {str(exc)}"
            }

    except Exception as exc:
        logger.exception("Error during candidate comparison: %s", exc)
        return {
            "status": "error",
            "error": "processing_failed",
            "reason": f"Internal error: {str(exc)}"
        }
