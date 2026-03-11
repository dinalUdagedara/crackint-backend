"""
Skill-gap analysis: compare resume entities vs job entities.
Returns missing skills, weak experience/education, suggestions, severity, and alerts.
"""

import re
from typing import Any, Dict, List, Literal

# Entity mapping: resume key -> job key for comparison
RESUME_SKILL_KEY = "SKILL"
JOB_SKILLS_REQUIRED_KEY = "SKILLS_REQUIRED"
RESUME_EXPERIENCE_KEY = "EXPERIENCE"
JOB_EXPERIENCE_REQUIRED_KEY = "EXPERIENCE_REQUIRED"
RESUME_EDUCATION_KEY = "EDUCATION"
JOB_EDUCATION_REQUIRED_KEY = "EDUCATION_REQUIRED"


def _normalize_strings(items: List[str]) -> set:
    """Normalize strings for comparison: lowercase, strip, filter empty."""
    return {s.strip().lower() for s in items if isinstance(s, str) and s.strip()}


def _extract_years(text: str) -> List[float]:
    """Extract year numbers from text (e.g. '2+ years', '5 years', '3-5')."""
    if not text:
        return []
    years = []
    # Match patterns like "2+ years", "5 years", "3-5 years", "2-4 yrs"
    patterns = [
        r"(\d+)\+?\s*(?:years?|yrs?|y\.?)\b",
        r"(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)?",
        r"\b(\d+)\s*(?:years?|yrs?)\b",
    ]
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            groups = m.groups()
            if len(groups) == 1:
                try:
                    years.append(float(groups[0]))
                except (TypeError, ValueError):
                    pass
            elif len(groups) == 2:
                try:
                    lo, hi = float(groups[0]), float(groups[1])
                    years.append((lo + hi) / 2)
                except (TypeError, ValueError):
                    pass
    return years


def _skill_overlap(job_skill: str, resume_skills: set) -> bool:
    """Check if any resume skill reasonably matches job skill (substring or exact)."""
    js = job_skill.strip().lower()
    if not js:
        return False
    for rs in resume_skills:
        if js in rs or rs in js:
            return True
    return False


def analyze_skill_gap(
    resume_entities: Dict[str, List[str]],
    job_entities: Dict[str, List[str]],
) -> Dict[str, Any]:
    """
    Compare resume vs job entities. Returns:
    - missing_skills: list of job-required skills not found in resume
    - weak_experience: bool or message if experience seems insufficient
    - weak_education: bool or message if education seems insufficient
    - suggestions: actionable improvement suggestions
    - severity: "low" | "medium" | "high"
    - alerts: list of {type, message, severity}
    """
    resume_skills = _normalize_strings(resume_entities.get(RESUME_SKILL_KEY, []))
    job_skills = [
        s for s in job_entities.get(JOB_SKILLS_REQUIRED_KEY, [])
        if isinstance(s, str) and s.strip()
    ]
    missing_skills = [
        s for s in job_skills
        if not _skill_overlap(s, resume_skills)
    ]
    # Deduplicate by lowercase
    seen = set()
    unique_missing = []
    for s in missing_skills:
        k = s.strip().lower()
        if k not in seen:
            seen.add(k)
            unique_missing.append(s)

    resume_exp = resume_entities.get(RESUME_EXPERIENCE_KEY, [])
    job_exp_req = job_entities.get(JOB_EXPERIENCE_REQUIRED_KEY, [])
    job_years: List[float] = []
    for j in job_exp_req:
        if isinstance(j, str):
            job_years.extend(_extract_years(j))
    resume_years: List[float] = []
    for r in resume_exp:
        if isinstance(r, str):
            resume_years.extend(_extract_years(r))

    weak_experience = False
    weak_experience_msg = ""
    if job_years:
        req_min = min(job_years)
        has_years = max(resume_years) if resume_years else 0
        if has_years < req_min:
            weak_experience = True
            weak_experience_msg = f"Job may require ~{req_min:.0f}+ years; resume suggests ~{has_years:.0f}."

    resume_edu = " ".join(
        str(x).lower() for x in resume_entities.get(RESUME_EDUCATION_KEY, [])
    )
    job_edu_req = job_entities.get(JOB_EDUCATION_REQUIRED_KEY, [])
    job_edu_keywords = set()
    for j in job_edu_req:
        if isinstance(j, str):
            for w in re.findall(r"\b\w+\b", j.lower()):
                if len(w) > 2:
                    job_edu_keywords.add(w)
    weak_education = False
    weak_education_msg = ""
    if job_edu_keywords:
        resume_edu_words = set(re.findall(r"\b\w+\b", resume_edu))
        overlap = job_edu_keywords & resume_edu_words
        if len(overlap) < min(2, len(job_edu_keywords)):
            weak_education = True
            weak_education_msg = "Education section may not clearly match job requirements."

    suggestions: List[str] = []
    if unique_missing:
        skills_str = ", ".join(unique_missing[:8])
        if len(unique_missing) > 8:
            skills_str += f" (+{len(unique_missing) - 8} more)"
        suggestions.append(f"Consider adding or highlighting these skills: {skills_str}.")
    if weak_experience and weak_experience_msg:
        suggestions.append(f"Experience: {weak_experience_msg}")
    if weak_education and weak_education_msg:
        suggestions.append(f"Education: {weak_education_msg}")

    # Severity
    n_missing = len(unique_missing)
    severity: Literal["low", "medium", "high"] = "low"
    if n_missing >= 5 or (weak_experience and weak_education):
        severity = "high"
    elif n_missing >= 2 or weak_experience or weak_education:
        severity = "medium"

    alerts: List[Dict[str, str]] = []
    if unique_missing:
        alerts.append({
            "type": "missing_skill",
            "message": f"Missing {len(unique_missing)} required skill(s): {', '.join(unique_missing[:5])}{'...' if len(unique_missing) > 5 else ''}",
            "severity": "high" if n_missing >= 5 else "medium",
        })
    if weak_experience:
        alerts.append({
            "type": "weak_experience",
            "message": weak_experience_msg,
            "severity": "medium",
        })
    if weak_education:
        alerts.append({
            "type": "weak_education",
            "message": weak_education_msg,
            "severity": "low",
        })

    return {
        "missing_skills": unique_missing,
        "weak_experience": weak_experience,
        "weak_experience_message": weak_experience_msg or None,
        "weak_education": weak_education,
        "weak_education_message": weak_education_msg or None,
        "suggestions": suggestions,
        "severity": severity,
        "alerts": alerts,
    }
