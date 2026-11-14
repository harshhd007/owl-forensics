#!/usr/bin/env python3
"""Build a fresh, deduplicated OWL Forensics live-jobs snapshot."""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "jobs-feed.json"
NOW = dt.datetime.now(dt.timezone.utc)
SECURITY = re.compile(r"\b(cyber(?:[ -]?security)?|information security|infosec|soc analyst|security (?:operations|analyst|engineer|researcher)|incident response|dfir|threat intelligence|penetration test(?:er|ing)?|pen test|red team|blue team|digital forensics|computer forensics|mobile forensics|e[- ]discovery|forensic examiner|malware analyst|vulnerability analyst)\b", re.I)
FORENSICS = re.compile(r"\b(forensic|forensics|dfir|incident response|e[- ]discovery|digital evidence|computer forensics|mobile forensics)\b", re.I)
INDIA = re.compile(r"\b(india|indian|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|gurugram|gurgaon|noida|chennai|kolkata|ahmedabad|kochi|jaipur)\b", re.I)
ANYWHERE = re.compile(r"\b(worldwide|anywhere|global|work from anywhere|remote worldwide)\b", re.I)


def request_json(url, data=None, headers=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "OWLForensicsJobs/1.0 (+https://owlforensics.in)", **(headers or {})})
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.load(response)


def parse_date(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except (ValueError, TypeError):
        try:
            return dt.datetime.fromtimestamp(float(value), dt.timezone.utc)
        except (ValueError, TypeError, OSError):
            return None


def clean_text(value):
    value = re.sub(r"<[^>]*>", " ", html.unescape(str(value or "")))
    return re.sub(r"\s+", " ", value).strip()


def normalize(title, company, location, description, url, source, posted, employment="", workplace="", salary=""):
    title, company, location = clean_text(title), clean_text(company), clean_text(location)
    description, url = clean_text(description), str(url or "").strip()
    if not title or not url or not url.startswith(("https://", "http://")):
        return None
    text = f"{title} {description}"
    # Require the role title itself to be security/forensics-related; a generic
    # marketing or sales role mentioning a security product in its description
    # is not a security vacancy.
    if not SECURITY.search(title):
        return None
    # Jobs must name India or be explicitly open worldwide/anywhere. Generic
    # "remote" posts are not assumed to accept applicants from India.
    place = f"{location} {title} {description[:500]}"
    india_ok = bool(INDIA.search(location)) or bool(ANYWHERE.search(place))
    if not india_ok:
        return None
    date = parse_date(posted)
    if date and date < NOW - dt.timedelta(days=14):
        return None
    if not date:
        date = NOW
    if ANYWHERE.search(place) and "remote" not in location.lower():
        location = (location + " · Remote worldwide").strip(" ·")
    elif "remote" in location.lower() and not INDIA.search(location) and ANYWHERE.search(place):
        location = "Remote · Worldwide"
    if len(description) > 420:
        description = description[:417].rsplit(" ", 1)[0] + "…"
    return {
        "id": re.sub(r"[^a-z0-9]+", "-", (source + "-" + url).lower()).strip("-")[:120],
        "title": title, "company": company or "Employer not listed", "location": location or "India",
        "description": description or "View the original listing for role details.", "url": url,
        "source": source, "postedAt": date.isoformat(), "employment": clean_text(employment),
        "workplace": clean_text(workplace), "salary": clean_text(salary),
        "specialty": "Digital forensics" if FORENSICS.search(text) else "Cybersecurity",
    }


def fetch_jooble(key):
    if not key:
        return []
    queries = ["cybersecurity", "SOC analyst", "digital forensics", "DFIR incident response", "information security", "threat intelligence", "penetration testing"]
    rows = []
    for term in queries:
        payload = request_json("https://in.jooble.org/api/" + urllib.parse.quote(key, safe=""),
                               {"keywords": term, "location": "India", "page": "1"},
                               {"Content-Type": "application/json"})
        for job in payload.get("jobs", []):
            normalized = normalize(job.get("title"), job.get("company"), job.get("location") or "India",
                                   job.get("snippet") or job.get("description"), job.get("link"), "Jooble",
                                   job.get("updated") or job.get("date"), job.get("type"), "", job.get("salary"))
            if normalized:
                rows.append(normalized)
    return rows


def fetch_jobicy():
    data = request_json("https://jobicy.com/api/jobs?count=200&geo=anywhere")
    rows = []
    for job in data.get("jobs", []):
        geo = clean_text(job.get("jobGeo"))
        remote = "remote" in " ".join(job.get("jobType") or []).lower()
        if not (INDIA.search(geo) or ANYWHERE.search(geo)):
            continue
        location = geo or ("Remote · Worldwide" if remote else "")
        summary = job.get("jobExcerpt") or job.get("jobDescription")
        normalized = normalize(job.get("jobTitle"), job.get("companyName"), location, summary,
                               job.get("url"), "Jobicy", job.get("pubDate"),
                               ", ".join(job.get("jobType") or []), "Remote" if remote else "", "")
        if normalized:
            rows.append(normalized)
    return rows


def fetch_remoteok():
    data = request_json("https://remoteok.com/api", headers={"Accept": "application/json"})
    rows = []
    for job in data[1:] if isinstance(data, list) else []:
        location = clean_text(job.get("location"))
        if not (INDIA.search(location) or ANYWHERE.search(location)):
            continue
        normalized = normalize(job.get("position"), job.get("company"), location,
                               job.get("description"), job.get("url") or job.get("apply_url"),
                               "Remote OK", job.get("date"), job.get("employment_type"), "Remote", job.get("salary"))
        if normalized:
            rows.append(normalized)
    return rows


def fetch_himalayas():
    """Read Himalayas' public API and keep only posts eligible in India."""
    queries = ["cybersecurity", "cyber security", "digital forensics", "forensic analyst",
               "security analyst", "security engineer", "security operations", "SOC analyst",
               "incident response", "DFIR", "penetration testing", "malware analyst",
               "threat intelligence", "information security", "security specialist",
               "cybersecurity analyst", "vulnerability analyst"]
    rows = []
    for term in queries:
        params = urllib.parse.urlencode({"q": term, "country": "IN", "sort": "recent", "page": 1})
        data = request_json("https://himalayas.app/jobs/api/search?" + params)
        for job in data.get("jobs", []):
            restrictions = job.get("locationRestrictions") or []
            allowed = not restrictions or any(
                (str(item.get("alpha2", "")).upper() == "IN" or "india" in str(item.get("name", "")).lower())
                if isinstance(item, dict) else "india" in str(item).lower()
                for item in restrictions
            )
            if not allowed:
                continue
            location = "Remote · Worldwide" if not restrictions else "Remote · India"
            salary = ""
            if job.get("minSalary") or job.get("maxSalary"):
                low, high = job.get("minSalary"), job.get("maxSalary")
                band = f"{low:,}" if low else ""
                if high:
                    band += ("–" if band else "") + f"{high:,}"
                salary = " ".join(part for part in [job.get("currency", ""), band, job.get("salaryPeriod", "")] if part)
            published = job.get("pubDate")
            if published:
                try:
                    published = dt.datetime.fromtimestamp(float(published), dt.timezone.utc).isoformat()
                except (ValueError, TypeError, OSError):
                    pass
            normalized = normalize(
                job.get("title"), job.get("companyName"), location,
                job.get("excerpt") or job.get("description"),
                job.get("applicationLink"), "Himalayas", published,
                job.get("employmentType", ""), "Remote", salary,
            )
            if normalized:
                normalized["id"] = "himalayas-" + str(job.get("guid") or normalized["id"])
                rows.append(normalized)
    return rows


def main():
    rows, errors = [], []
    for name, fetch in (("Jooble", lambda: fetch_jooble(os.getenv("JOOBLE_API_KEY", ""))),
                        ("Himalayas", fetch_himalayas),
                        ("Jobicy", fetch_jobicy), ("Remote OK", fetch_remoteok)):
        try:
            rows.extend(fetch())
        except Exception as exc:  # Keep the daily workflow useful if one upstream is down.
            print(f"{name} feed unavailable: {exc}", file=sys.stderr)
            errors.append(name)
    unique = {}
    for job in rows:
        key = re.sub(r"[^a-z0-9]", "", job["url"].lower())
        unique.setdefault(key, job)
    jobs = sorted(unique.values(), key=lambda item: item["postedAt"], reverse=True)
    result = {
        "updatedAt": NOW.isoformat(),
        "count": len(jobs),
        "target": 25,
        "targetReached": len(jobs) >= 25,
        "sources": sorted({job["source"] for job in jobs}),
        "sourceErrors": errors,
        "jobs": jobs,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(jobs)} current, India-eligible forensic/cybersecurity jobs (target: 25).")


if __name__ == "__main__":
    main()
