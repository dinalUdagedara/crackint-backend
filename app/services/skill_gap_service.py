"""
Skill-gap analysis: compare resume entities vs job entities.
Returns missing skills, weak experience/education, suggestions, severity, and alerts.
Includes optional location suitability (remote vs on-site, distance vs candidate location).
"""

import re
from typing import Any, Dict, List, Literal, Tuple

# Entity mapping: resume key -> job key for comparison
RESUME_SKILL_KEY = "SKILL"
JOB_SKILLS_REQUIRED_KEY = "SKILLS_REQUIRED"
RESUME_EXPERIENCE_KEY = "EXPERIENCE"
JOB_EXPERIENCE_REQUIRED_KEY = "EXPERIENCE_REQUIRED"
RESUME_EDUCATION_KEY = "EDUCATION"
JOB_EDUCATION_REQUIRED_KEY = "EDUCATION_REQUIRED"

# Job entity keys for location suitability
JOB_LOCATION_KEY = "LOCATION"
JOB_TYPE_KEY = "JOB_TYPE"

REMOTE_KEYWORDS = frozenset(
    {
        "remote",
        "work from home",
        "wfh",
        "work from anywhere",
        "distributed",
        "anywhere",
        "home-based",
        "home based",
    }
)

# Areas considered "same metro" (~within 30 km): job and candidate in same set → suitability "good"
# Extend with more cities as needed; names are normalized (lowercase, no extra spaces).
SAME_METRO_AREAS = [
    # Colombo metro (Sri Lanka): Galkissa, Dematagoda, Colombo, Dehiwala, etc.
    frozenset(
        {
            "colombo",
            "colombo fort",
            "fort",
            "galkissa",
            "dehiwala",
            "dematagoda",
            "kotte",
            "kaduwela",
            "maharagama",
            "malabe",
            "boralesgamuwa",
            "borella",
            "nugegoda",
            "kohuwala",
            "battaramulla",
            "rajagiriya",
            "ja-ela",
            "wattala",
            "kelaniya",
            "moratuwa",
            "panadura",
            "mt lavinia",
            "mount lavinia",
            "wellawatta",
            "bambalapitiya",
            "kollupitiya",
            "slave island",
            "maradana",
            "pettah",
        }
    ),
]


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


def _text_indicates_remote(text: str) -> bool:
    """True if text suggests remote work (case-insensitive)."""
    if not text or not isinstance(text, str):
        return False
    t = text.strip().lower()
    return any(kw in t for kw in REMOTE_KEYWORDS)


def _normalize_location_for_compare(loc: str) -> str:
    """Normalize location string for rough comparison: lowercase, strip."""
    if not loc or not isinstance(loc, str):
        return ""
    return loc.strip().lower()


def _extract_place_key(loc: str) -> str:
    """Extract a single place name for metro matching (e.g. 'No 25 House Road, Dematagoda' -> 'dematagoda', 'Galkissa, Sri Lanka' -> 'galkissa')."""
    n = _normalize_location_for_compare(loc)
    if not n:
        return ""
    parts = [p.strip() for p in n.split(",") if p.strip()]
    if not parts:
        return ""
    # Skip street-style parts (e.g. "no 25 house road"); take first part that looks like a place name
    for p in parts:
        if re.search(r"[a-z]", p) and not re.match(r"^(no\.?|\d+)\s", p):
            return p.strip()
    return parts[-1].strip()


def _same_metro(candidate_loc: str, job_loc: str) -> bool:
    """True if both locations are in the same metro (e.g. within ~30 km): same SAME_METRO_AREAS set."""
    c_key = _extract_place_key(candidate_loc)
    j_key = _extract_place_key(job_loc)
    if not c_key or not j_key:
        return False
    if c_key == j_key or c_key in j_key or j_key in c_key:
        return True
    for metro in SAME_METRO_AREAS:
        if c_key in metro and j_key in metro:
            return True
    return False


def _same_region(candidate_loc: str, job_loc: str) -> bool:
    """
    True if same country/overlap or same metro (within ~30 km).
    """
    c = _normalize_location_for_compare(candidate_loc)
    j = _normalize_location_for_compare(job_loc)
    if not c or not j:
        return False
    if _same_metro(candidate_loc, job_loc):
        return True
    if c == j or c in j or j in c:
        return True
    c_part = c.split(",")[-1].strip() if "," in c else c
    j_part = j.split(",")[-1].strip() if "," in j else j
    return c_part == j_part or c_part in j_part or j_part in c_part


def analyze_location_suitability(
    job_location_str: str | None,
    job_entities: Dict[str, List[str]],
    candidate_location: str | None,
) -> Tuple[Dict[str, Any], Dict[str, str] | None]:
    """
    Parse job location (city, country, remote/on-site) and compare with candidate location.
    Returns (location_suitability_dict, optional_alert).
    - If remote → suitability "good", highlight_remote_match True, no relocation alert.
    - If non-remote and candidate location far → suitability "caution", alert.
    - If no candidate location → suitability "unknown".
    """
    loc_list = job_entities.get(JOB_LOCATION_KEY, []) or []
    type_list = job_entities.get(JOB_TYPE_KEY, []) or []
    job_display = job_location_str or ""
    if not job_display and loc_list:
        job_display = ", ".join(str(x).strip() for x in loc_list if x)
    if not job_display and type_list:
        job_display = " ".join(str(x).strip() for x in type_list if x)

    is_remote = _text_indicates_remote(job_display)
    for t in type_list:
        if isinstance(t, str) and _text_indicates_remote(t):
            is_remote = True
            break
    for loc in loc_list:
        if isinstance(loc, str) and _text_indicates_remote(loc):
            is_remote = True
            break

    if is_remote:
        payload = {
            "job_location_display": job_display or "Remote",
            "is_remote": True,
            "candidate_location": candidate_location,
            "suitability": "good",
            "message": "Remote role — location is not a barrier.",
            "highlight_remote_match": True,
        }
        return payload, None

    if not candidate_location or not _normalize_location_for_compare(
        candidate_location
    ):
        payload = {
            "job_location_display": job_display,
            "is_remote": False,
            "candidate_location": candidate_location,
            "suitability": "unknown",
            "message": "Add your location to see if this job is practical for you.",
            "highlight_remote_match": False,
        }
        return payload, None

    job_loc_combined = job_display or " ".join(str(x) for x in loc_list if x)
    same_region = (
        _same_region(candidate_location, job_loc_combined)
        if job_loc_combined
        else False
    )

    if same_region:
        within_reasonable = _same_metro(candidate_location, job_loc_combined)
        payload = {
            "job_location_display": job_display,
            "is_remote": False,
            "candidate_location": candidate_location,
            "suitability": "good",
            "message": (
                "Job is within a reasonable distance."
                if within_reasonable
                else "Job location appears to be in your region."
            ),
            "highlight_remote_match": False,
        }
        return payload, None

    alert = {
        "type": "location_mismatch",
        "message": "This job may not be practical unless relocation is possible.",
        "severity": "medium",
    }
    payload = {
        "job_location_display": job_display,
        "is_remote": False,
        "candidate_location": candidate_location,
        "suitability": "caution",
        "message": "This job may not be practical unless relocation is possible.",
        "highlight_remote_match": False,
    }
    return payload, alert


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
        s
        for s in job_entities.get(JOB_SKILLS_REQUIRED_KEY, [])
        if isinstance(s, str) and s.strip()
    ]
    missing_skills = [s for s in job_skills if not _skill_overlap(s, resume_skills)]
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
            weak_education_msg = (
                "Education section may not clearly match job requirements."
            )

    suggestions: List[str] = []
    if unique_missing:
        skills_str = ", ".join(unique_missing[:8])
        if len(unique_missing) > 8:
            skills_str += f" (+{len(unique_missing) - 8} more)"
        suggestions.append(
            f"Consider adding or highlighting these skills: {skills_str}."
        )
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
        alerts.append(
            {
                "type": "missing_skill",
                "message": f"Missing {len(unique_missing)} required skill(s): {', '.join(unique_missing[:5])}{'...' if len(unique_missing) > 5 else ''}",
                "severity": "high" if n_missing >= 5 else "medium",
            }
        )
    if weak_experience:
        alerts.append(
            {
                "type": "weak_experience",
                "message": weak_experience_msg,
                "severity": "medium",
            }
        )
    if weak_education:
        alerts.append(
            {
                "type": "weak_education",
                "message": weak_education_msg,
                "severity": "low",
            }
        )

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
