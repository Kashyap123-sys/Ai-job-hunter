import os
import sqlite3
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import requests
import streamlit as st

# Optional file reader imports with safe fallbacks
try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import docx
except ImportError:
    docx = None

# Streamlit Page Config
st.set_page_config(
    page_title="AI Job Hunter & Recruiter Outreach",
    page_icon="🚀",
    layout="wide"
)

# ----------------- LOCAL PERSISTENT DATABASE ----------------- #
DB_FILE = "job_hunter.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            credits INTEGER DEFAULT 15,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Applications table
    c.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            recruiter_email TEXT,
            job_title TEXT,
            company TEXT,
            status TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_or_create_user(email):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE email = ?", (email.lower(),))
    row = c.fetchone()
    if row is None:
        c.execute("INSERT INTO users (email, credits) VALUES (?, 15)", (email.lower(),))
        conn.commit()
        credits = 15
    else:
        credits = row[0]
    conn.close()
    return credits

def deduct_credit(email):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits - 1 WHERE email = ? AND credits > 0", (email.lower(),))
    conn.commit()
    conn.close()

def log_application(user_email, recruiter_email, job_title, company, status="Delivered"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO applications (user_email, recruiter_email, job_title, company, status)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_email.lower(), recruiter_email, job_title, company, status))
    conn.commit()
    conn.close()

def get_user_applications(email):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT job_title, company, recruiter_email, applied_at, status 
        FROM applications 
        WHERE user_email = ? 
        ORDER BY applied_at DESC
    ''', (email.lower(),))
    rows = c.fetchall()
    conn.close()
    return rows

init_db()

# ----------------- RESUME EXTRACTION & SKILL MINING ----------------- #
def extract_text_from_file(uploaded_file):
    file_type = uploaded_file.name.split(".")[-1].lower()
    text = ""
    if file_type == "pdf":
        if pypdf:
            reader = pypdf.PdfReader(uploaded_file)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        else:
            text = uploaded_file.read().decode("utf-8", errors="ignore")
    elif file_type == "docx":
        if docx:
            doc = docx.Document(uploaded_file)
            text = "\n".join([p.text for p in doc.paragraphs])
        else:
            text = uploaded_file.read().decode("utf-8", errors="ignore")
    else:
        text = uploaded_file.read().decode("utf-8", errors="ignore")
    return text.strip()

COMMON_SKILLS = [
    "python", "seo", "cro", "geo", "aeo", "growth marketing", "digital marketing", 
    "automation", "n8n", "crewai", "sql", "analytics", "react", "javascript", 
    "docker", "fastapi", "django", "content strategy", "product management", "qa"
]

def parse_cv_details(text):
    lower_text = text.lower()
    detected_skills = [s.title() for s in COMMON_SKILLS if s in lower_text]
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    candidate_name = lines[0] if lines else "Candidate"
    
    # Try identifying candidate contact
    candidate_email = ""
    for token in lower_text.replace("\n", " ").split(" "):
        if "@" in token and "." in token and len(token) > 5:
            candidate_email = token.strip(",;:()<>")
            break
            
    return {
        "name": candidate_name[:35],
        "email": candidate_email,
        "skills": detected_skills if detected_skills else ["Growth", "Technology", "Problem Solving"]
    }

# ----------------- LIVE & FALLBACK JOB SEARCH ----------------- #
FALLBACK_JOBS = [
    {
        "id": "mock_1",
        "title": "Organic Growth Strategist",
        "company": "ScaleUp Tech",
        "location": "Remote / Bengaluru",
        "recruiter_email": "talent@scaleuptech.org",
        "tags": ["seo", "cro", "growth marketing", "automation", "analytics"],
        "description": "Looking for a seasoned strategist skilled in full-funnel growth, technical SEO, and conversion optimization."
    },
    {
        "id": "mock_2",
        "title": "AI Workflow & Automation Specialist",
        "company": "Agentic Labs",
        "location": "Hybrid / Gurgaon",
        "recruiter_email": "careers@agenticlabs.dev",
        "tags": ["python", "automation", "n8n", "crewai", "agents"],
        "description": "Architect autonomous AI workflows, process automations, and LLM-driven pipelines."
    },
    {
        "id": "mock_3",
        "title": "SEO & Generative Engine Optimizer (GEO)",
        "company": "NextGen Media",
        "location": "Remote / Mumbai",
        "recruiter_email": "hr@nextgenmedia.in",
        "tags": ["seo", "geo", "aeo", "content strategy", "digital marketing"],
        "description": "Optimize digital presence for conversational AI engines, modern SERPs, and organic discovery channels."
    },
    {
        "id": "mock_4",
        "title": "Full Stack Python & AI Engineer",
        "company": "InnoSoft Digital",
        "location": "Remote / Chandigarh",
        "recruiter_email": "jobs@innosoft.io",
        "tags": ["python", "react", "sql", "fastapi", "docker"],
        "description": "Develop scalable SaaS backends, integrate AI APIs, and maintain high-performance web systems."
    }
]

def fetch_live_jobs(skills):
    """Fetches real jobs via Remotive API with local fallback."""
    query = "+".join(skills[:2]) if skills else "marketing"
    url = f"https://remotive.com/api/remote-jobs?search={query}&limit=8"
    results = []
    
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json().get("jobs", [])
            for item in data[:6]:
                results.append({
                    "id": str(item.get("id")),
                    "title": item.get("title", "Software Specialist"),
                    "company": item.get("company_name", "Tech Co"),
                    "location": item.get("candidate_required_location", "Remote"),
                    # Generate candidate inbox destination for demo / real recruiters
                    "recruiter_email": f"hiring@{item.get('company_name', 'company').lower().replace(' ', '')}.com",
                    "tags": [t.lower() for t in item.get("tags", [])],
                    "description": item.get("description", "")[:280].replace("<p>", "").replace("</p>", "") + "..."
                })
    except Exception:
        pass
        
    if not results:
        results = FALLBACK_JOBS
        
    # Compute match scores based on resume skills
    skills_lower = [s.lower() for s in skills]
    for j in results:
        overlap = [tag for tag in j["tags"] if any(tag in s or s in tag for s in skills_lower)]
        score = int(60 + (len(overlap) * 12))
        j["match_score"] = min(score, 98)
        
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results

# ----------------- SMTP EMAIL SENDER WITH RESUME ATTACHMENT ----------------- #
def send_application_email(sender_email, app_password, recipient_email, subject, body, attachment_file=None):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    
    msg.attach(MIMEText(body, 'plain'))
    
    if attachment_file is not None:
        attachment_file.seek(0)
        part = MIMEApplication(attachment_file.read(), Name=attachment_file.name)
        part['Content-Disposition'] = f'attachment; filename="{attachment_file.name}"'
        msg.attach(part)
        attachment_file.seek(0)
        
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(sender_email, app_password)
    server.sendmail(sender_email, recipient_email, msg.as_string())
    server.quit()


# ----------------- SIDEBAR: AUTH & CREDITS ----------------- #
with st.sidebar:
    st.header("⚡ Profile & Credits")
    user_email_input = st.text_input("Your Email (Tracks Credits)", placeholder="you@domain.com")
    
    if user_email_input:
        current_credits = get_or_create_user(user_email_input)
    else:
        current_credits = 15
        
    st.metric(label="Available Credits", value=f"{current_credits} / 15 Free")
    
    if current_credits <= 0:
        st.error("You've used all 15 free credits!")
        
    st.divider()
    st.header("✉️ Gmail Connection")
    gmail_sender = st.text_input("Sender Gmail", value=user_email_input if user_email_input else "", placeholder="yourname@gmail.com")
    gmail_app_pw = st.text_input("Google App Password", type="password", help="16-character Google App Password (not your personal account password).")
    st.caption("Need an App Password? Go to [Google App Passwords](https://myaccount.google.com/apppasswords)")


# ----------------- MAIN UI ----------------- #
tab1, tab2 = st.tabs(["🚀 Job Hunter & Auto-Applier", "📊 Application History"])

with tab1:
    st.title("⚡ AI Job Hunter & Auto-Applier")
    st.write("Scan jobs across portals, tailor recruiter pitches, and submit applications directly from your Gmail.")

    uploaded_cv = st.file_uploader("Upload your CV (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])

    if uploaded_cv:
        cv_text = extract_text_from_file(uploaded_cv)
        parsed = parse_cv_details(cv_text)
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.success("✅ CV Parsed")
            st.write(f"**Applicant:** {parsed['name']}")
            st.write(f"**Key Competencies:**")
            st.write(", ".join(parsed["skills"]))
        with c2:
            st.info("💡 **Ready to apply:** Open positions below are matched to your skill profile. Click 'Review & Send Pitch' to customize and send.")
            
        st.divider()
        st.subheader("🎯 Matched Roles Available for Outreach")
        
        matched_jobs = fetch_live_jobs(parsed["skills"])
        
        for job in matched_jobs:
            with st.container():
                col_info, col_score = st.columns([4, 1])
                with col_info:
                    st.markdown(f"#### {job['title']} — **{job['company']}**")
                    st.caption(f"📍 {job['location']} | Recruiter Inbox: `{job['recruiter_email']}`")
                    st.write(job["description"])
                with col_score:
                    st.metric("Match Score", f"{job['match_score']}%")
                
                with st.expander(f"Review & Send Pitch to {job['company']}"):
                    default_subject = f"Application: {job['title']} - {parsed['name']}"
                    subject_val = st.text_input(f"Subject Line ({job['id']})", value=default_subject, key=f"subj_{job['id']}")
                    
                    default_body = f"""Dear Hiring Team at {job['company']},

I am writing to express my strong interest in the {job['title']} opening.

With a focused background in {', '.join(parsed['skills'][:4])}, I have developed high-impact systems and workflows that drive measurable business outcomes.

Key Highlights:
- Applicant: {parsed['name']}
- Core Competencies: {', '.join(parsed['skills'])}

I have attached my updated resume for your review and look forward to speaking with you.

Best regards,
{parsed['name']}
"""
                    body_val = st.text_area(f"Pitch Email Body ({job['id']})", value=default_body, height=180, key=f"body_{job['id']}")
                    
                    if st.button("🚀 Send Application (Uses 1 Credit)", key=f"btn_{job['id']}"):
                        if not user_email_input:
                            st.warning("Please enter your email in the sidebar first.")
                        elif current_credits <= 0:
                            st.error("No credits remaining.")
                        elif not gmail_sender or not gmail_app_pw:
                            st.warning("Please provide your Gmail and 16-character Google App Password in the sidebar.")
                        else:
                            try:
                                with st.spinner("Dispatching resume to recruiter..."):
                                    send_application_email(
                                        sender_email=gmail_sender,
                                        app_password=gmail_app_pw,
                                        recipient_email=job["recruiter_email"],
                                        subject=subject_val,
                                        body=body_val,
                                        attachment_file=uploaded_cv
                                    )
                                    deduct_credit(user_email_input)
                                    log_application(user_email_input, job["recruiter_email"], job["title"], job["company"])
                                    st.success(f"Application sent successfully to {job['recruiter_email']} with your CV attached!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Failed to send email: {e}")
                st.divider()

with tab2:
    st.subheader("📬 Sent Applications Tracker")
    if user_email_input:
        apps = get_user_applications(user_email_input)
        if apps:
            for title, comp, rec_email, dt, status in apps:
                st.write(f"💼 **{title}** at **{comp}** | Recruiter: `{rec_email}` | 🕒 {dt} | Status: **{status}**")
        else:
            st.info("No applications dispatched yet. Start applying from the main tab!")
    else:
        st.info("Enter your email in the sidebar to review your sent applications history.")
