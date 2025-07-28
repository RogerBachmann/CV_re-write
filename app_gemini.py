# -------------------------------------
# 1. SETUP AND IMPORTS
# -------------------------------------
import streamlit as st
import os
import google.generativeai as genai
import pdfplumber
from docx import Document
from docxtpl import DocxTemplate
import io
import json

# -------------------------------------
# 2. GEMINI API CONFIGURATION
# -------------------------------------
st.set_page_config(layout="wide")
try:
    # Use st.secrets for deployment. This is the correct way for Streamlit Cloud.
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    # This error will show on the login page if secrets are not set correctly.
    st.error("🔴 Critical Error: Cannot connect to AI service. Please contact the administrator.")
    st.stop()

# -------------------------------------
# 3. HELPER FUNCTIONS
# -------------------------------------

def extract_text_from_file(uploaded_file):
    """Extracts text from an uploaded PDF or DOCX file."""
    try:
        if uploaded_file.type == "application/pdf":
            with pdfplumber.open(uploaded_file) as pdf:
                return "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            doc = Document(uploaded_file)
            return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        st.error(f"Error reading file: {uploaded_file.name}")
    return ""

def parse_and_rewrite_cv(consolidated_text, tone_selection):
    """The main AI function that parses, rewrites, and returns structured JSON."""
    prompt = f"""
    You are a Tier-1 executive career coach and CV writer, specializing in crafting documents for senior-level candidates targeting the Swiss, German, and Austrian markets. Your expertise is in transforming raw, informal career data into a polished, compelling, and strategically effective narrative.

    Your task is to analyze the CONSOLIDATED INPUT TEXT provided below. This text may contain a mix of information from a CV, a cover letter, a target job description, and personal notes. You must first synthesize all this information, then professionally rewrite the content according to the detailed rules below, and finally return the data as a single, clean JSON object.

    **JSON Structure Requirements (Strictly follow this):**
    The root JSON object must contain these keys: "personal_info", "summary_paragraphs", "languages", "skills", "work_experience", "education", "hobbies".

    1.  `personal_info`: An object with keys "NAME", "JOB_TITLE", "phone", "email", "city", "zip", "Linkedin".
    2.  `summary_paragraphs`: A list of strings, containing exactly two paragraphs.
    3.  `languages`: A list of objects, each with "language" and "level". Provide up to 3.
    4.  `skills`: A list of strings for skills. Provide up to 6.
    5.  `work_experience`: A list of objects. Each object must have keys: "company", "from", "to", "job_title", "responsibility", and "achievements". Provide up to 15 entries.
        - `achievements` MUST be a list of strings. Provide up to 3 achievement points per job, based on the input.
    6.  `education`: A list of objects, each with "degree", "graduation", "university", "university_location", "university_country". Provide up to 6.
    7.  `hobbies`: A list of strings for hobbies. Provide up to 3.

    ---

    **Master Objective:** The final output must read like it was written by a human expert. It must be strategic, persuasive, and reflect the candidate as a high-impact individual in their field.

    **Advanced Rewriting and Content Generation Rules:**

    **1. Tone and Language (CRITICAL):**
    - **Language:** Use British English.
    - **Contextual Analysis:** First, analyze all input. If a job description is included, tailor the CV's language and skills towards that job.
    - **Dynamic Tone Selection:** The user has selected the following tone: **'{tone_selection}'**. You MUST adapt your writing style accordingly.
        - If 'Executive / Leadership', use authoritative and strategic language suitable for C-level or management roles.
        - If 'Technical / Expert', focus on deep domain knowledge, specific technologies, and precise, data-driven language.
        - If 'Sales / Commercial', use persuasive, energetic language focused on growth, revenue, and client relationships.
    - **Final Polish:** It should be factual and confident, not boastful.

    **2. Professional Summary (`summary_paragraphs`):**
    - **Paragraph 1:** Start with a powerful "title-line" defining the candidate's professional identity (e.g., "Commercial Leader with 15 years of experience..."). Follow with their single most impressive, quantifiable achievement from their recent career. **Strictly adhere to a maximum of 310 characters (including spaces).** Be specific and concise.
    - **Paragraph 2:** Write from the first-person ("I") perspective. Synthesize the candidate's core motivators and values. If no information is provided, create a strong, fitting paragraph based on their profile. **Strictly adhere to a maximum of 160 characters (including spaces).**

    **3. Work Experience (`work_experience`):**
    - **Responsibility:** Write 1-2 concise sentences defining the scope and core purpose of the role. Quantify it immediately if possible (e.g., "Managed a team of 12 and a P&L of €5M across the DACH region...").
    - **Achievements:**
        - **Result-by-Action Framework:** Each bullet point must focus on the result. The preferred format is: "I achieved [Result] by [implementing, leading, creating a specific action]."
        - **Quantification:** Scour the input text for numbers, percentages, or scale indicators. **If numbers are present, you MUST use them.** If no numbers are present for an achievement, create a strong, descriptive, non-quantified achievement; do not invent numbers.
        - **Number of Bullet Points:** Generate up to 3 achievement bullet points per job, depending on the richness of the input provided for that role.

    **4. Negative Constraints (What to AVOID AT ALL COSTS):**
    - **No Passive Voice:** Change "was responsible for" to "Managed," "Oversaw," etc.
    - **NO BUZZWORDS:** Strictly avoid the following and similar empty phrases: seasoned, results-driven, dynamic, motivated, proven track record, passionate, innovative, creative thinker, strategic thinker, go-getter, self-starter, team player, leader of change, strong communicator, influencer, people-oriented, cross-functional collaborator, change agent. Demonstrate qualities, do not state them.

    **Final Instruction:** If information for any field is not found, use an empty string "" or an empty list []. Your entire output MUST be a single, valid JSON object and nothing else.

    CONSOLIDATED INPUT TEXT:
    ---
    {consolidated_text}
    ---
    """
    try:
        response = model.generate_content(prompt)
        json_text = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(json_text)
    except Exception as e:
        st.error(f"Error parsing or rewriting CV with Gemini: {e}")
        st.text_area("Model's Raw Output (for debugging):", response.text if 'response' in locals() else "No response", height=150)
    return None

def generate_word_document(context):
    """Renders the final context dictionary into the Word template."""
    try:
        doc = DocxTemplate("CVTemplate_Python.docx")
        doc.render(context)
        doc_buffer = io.BytesIO()
        doc.save(doc_buffer)
        doc_buffer.seek(0)
        return doc_buffer
    except Exception as e:
        st.error(f"Error generating Word doc: {e}. Check 'CVTemplate_Python.docx' exists and all placeholders match the form.")
    return None

# -------------------------------------
# 4. THE MAIN APPLICATION LOGIC
# This function contains your entire app. It will only run if the password is correct.
# -------------------------------------
def run_the_app():
    st.sidebar.success("✅ Logged in successfully!")
    st.title("🇨🇭 The Ultimate Swiss CV Enhancer")

    if 'cv_data' not in st.session_state:
        st.session_state.cv_data = None

    st.header("Step 1: Consolidate All Information")
    uploaded_files = st.file_uploader(
        "Upload relevant documents (CV, cover letter, job description, etc.)",
        type=["pdf", "docx"],
        accept_multiple_files=True
    )
    free_text_input = st.text_area("Paste any additional notes, text, or ideas here:", height=150)

    # NEW: Tone selection dropdown menu
    st.subheader("Select the Desired Tone")
    tone_selection = st.selectbox(
        "Choose the tone that best fits the target role:",
        ("Executive / Leadership", "Technical / Expert", "Sales / Commercial", "General Professional"),
        label_visibility="collapsed"
    )

    if st.button("🚀 Analyse All Info & Fill Form"):
        all_texts = []
        if uploaded_files:
            for file in uploaded_files:
                st.write(f"Reading file: `{file.name}`...")
                all_texts.append(extract_text_from_file(file))
        if free_text_input:
            all_texts.append(free_text_input)

        if not all_texts:
            st.warning("Please upload at least one file or provide some text.")
        else:
            consolidated_text = "\n\n--- DOCUMENT SEPARATOR ---\n\n".join(all_texts)
            with st.spinner("🤖 Gemini is synthesizing all info, rewriting, and structuring the CV..."):
                # MODIFIED: Pass the tone_selection to the function
                st.session_state.cv_data = parse_and_rewrite_cv(consolidated_text, tone_selection)

    if st.session_state.cv_data:
        st.success("✅ Success! The form below is now filled. Review the content before generating the document.")
        st.header("Step 2: Review, Edit, and Generate Final Document")

        data = st.session_state.cv_data
        
        with st.form(key='cv_template_form'):
            with st.expander("Personal Information", expanded=True):
                p_info = data.get('personal_info', {})
                p_info['NAME'] = st.text_input("Name (NAME)", value=p_info.get('NAME', ''))
                p_info['JOB_TITLE'] = st.text_input("Job Title (JOB_TITLE)", value=p_info.get('JOB_TITLE', ''))
                col1, col2, col3, col4 = st.columns(4)
                p_info['phone'] = col1.text_input("Phone (phone)", value=p_info.get('phone', ''))
                p_info['email'] = col2.text_input("Email (email)", value=p_info.get('email', ''))
                p_info['city'] = col3.text_input("City (city)", value=p_info.get('city', ''))
                p_info['zip'] = col4.text_input("ZIP Code (zip)", value=p_info.get('zip', ''))
                p_info['Linkedin'] = st.text_input("LinkedIn URL (Linkedin)", value=p_info.get('Linkedin', ''))

            with st.expander("Professional Summary", expanded=True):
                summary_paras = data.get('summary_paragraphs', [])
                while len(summary_paras) < 2: summary_paras.append('')
                summary_paras[0] = st.text_area("Summary Paragraph 1", value=summary_paras[0], height=100)
                summary_paras[1] = st.text_area("Summary Paragraph 2", value=summary_paras[1], height=100)

            with st.expander("Work Experience", expanded=True):
                work_experience = data.get('work_experience', [])
                # NEW: Limit the number of experience entries displayed to 15
                for i, exp in enumerate(work_experience[:15]):
                    st.subheader(f"Work Experience #{i+1}")
                    exp['company'] = st.text_input(f"Company", value=exp.get('company', ''), key=f"c_{i}")
                    exp['job_title'] = st.text_input(f"Job Title", value=exp.get('job_title', ''), key=f"t_{i}")
                    col1, col2 = st.columns(2)
                    exp['from'] = col1.text_input(f"Start Date", value=exp.get('from', ''), key=f"from_{i}")
                    exp['to'] = col2.text_input(f"End Date", value=exp.get('to', ''), key=f"to_{i}")
                    exp['responsibility'] = st.text_area(f"Responsibility", value=exp.get('responsibility', ''), height=80, key=f"resp_{i}")
                    st.markdown("**Achievements:**")
                    achievements = exp.get('achievements', [])
                    while len(achievements) < 3: achievements.append('')
                    exp['achievements'] = achievements
                    for j in range(3):
                        achievements[j] = st.text_input(f"Achievement {j+1}", value=achievements[j], key=f"ach_{i}_{j}")
                    st.markdown("---")

            col1, col2 = st.columns(2)
            with col1:
                with st.expander("Skills"):
                    skills = data.get('skills', [])
                    # NEW: Expand skills to handle up to 6
                    while len(skills) < 6: skills.append('')
                    for i in range(6): skills[i] = st.text_input(f"Skill {i+1}", value=skills[i], key=f"skill_{i}")
            with col2:
                with st.expander("Languages"):
                    languages = data.get('languages', [])
                    while len(languages) < 3: languages.append({'language':'', 'level':''})
                    for i in range(3):
                        lang_obj = languages[i]
                        c1, c2 = st.columns(2)
                        lang_obj['language'] = c1.text_input(f"Language {i+1}", value=lang_obj.get('language',''), key=f"lang_{i}")
                        lang_obj['level'] = c2.text_input(f"Level {i+1}", value=lang_obj.get('level',''), key=f"level_{i}")
            
            with st.expander("Education & Qualifications"):
                education = data.get('education', [])
                # NEW: Expand education to handle up to 6
                while len(education) < 6: education.append({})
                for i, edu in enumerate(education[:6]):
                    st.subheader(f"Education #{i+1}")
                    edu['degree'] = st.text_input(f"Degree", value=edu.get('degree',''), key=f"deg_{i}")
                    edu['graduation'] = st.text_input(f"Graduation Year", value=edu.get('graduation',''), key=f"grad_{i}")
                    edu['university'] = st.text_input(f"University", value=edu.get('university',''), key=f"uni_{i}")
                    c1,c2 = st.columns(2)
                    edu['university_location'] = c1.text_input(f"Location", value=edu.get('university_location',''), key=f"uniloc_{i}")
                    edu['university_country'] = c2.text_input(f"Country", value=edu.get('university_country',''), key=f"unicoun_{i}")

            with st.expander("Hobbies & Extracurricular"):
                hobbies = data.get('hobbies', [])
                while len(hobbies) < 3: hobbies.append('')
                for i in range(3): hobbies[i] = st.text_input(f"Hobby {i+1}", value=hobbies[i], key=f"hobby_{i}")


            submit_button = st.form_submit_button(label='📄 Generate Final Word Document')

        if submit_button:
            # This logic remains largely the same, but now respects the larger number of items
            final_context = {}
            final_context.update(data.get('personal_info', {}))
            summary_paras = data.get('summary_paragraphs', ['',''])
            final_context['summary_paragraph_1'] = summary_paras[0]
            final_context['summary_paragraph_2'] = summary_paras[1]
            for i, exp in enumerate(data.get('work_experience', [])[:15]):
                final_context[f'company_{i+1}'] = exp.get('company')
                final_context[f'from_{i+1}'] = exp.get('from')
                final_context[f'to_{i+1}'] = exp.get('to')
                final_context[f'job_title_{i+1}'] = exp.get('job_title')
                final_context[f'responsibility_{i+1}'] = exp.get('responsibility')
                for j, ach in enumerate(exp.get('achievements', [])):
                    final_context[f'achievement_job_{i+1}_{j+1}'] = ach
            for i, lang in enumerate(data.get('languages', [])[:3]):
                final_context[f'language_{i+1}'] = lang.get('language')
                final_context[f'level_{i+1}'] = lang.get('level')
            for i, skill in enumerate(data.get('skills', [])[:6]):
                final_context[f'skill_{i+1}'] = skill
            for i, edu in enumerate(data.get('education', [])[:6]):
                final_context[f'degree_{i+1}'] = edu.get('degree')
                final_context[f'graduation_{i+1}'] = edu.get('graduation')
                final_context[f'university_{i+1}'] = edu.get('university')
                final_context[f'university_location_{i+1}'] = edu.get('university_location')
                final_context[f'university_country_{i+1}'] = edu.get('university_country')
            for i, hobby in enumerate(data.get('hobbies', [])[:3]):
                final_context[f'hobby_{i+1}'] = hobby

            with st.spinner("Creating your polished Word document..."):
                doc_buffer = generate_word_document(final_context)
                if doc_buffer:
                    st.success("🎉 Your CV has been generated!")
                    st.download_button(
                        label="⬇️ Download Final CV",
                        data=doc_buffer,
                        file_name=f"CV_{final_context.get('NAME', 'candidate').replace(' ', '_')}.docx"
                    )

# -------------------------------------
# 5. PASSWORD CHECK
# This part now runs first when a user visits the page.
# -------------------------------------
def check_password():
    """Returns `True` if the user entered the correct password."""
    try:
        st.title("🔐 Secure Access")
        password = st.text_input("Please enter the password to access the tool:", type="password")
        if password == st.secrets["APP_PASSWORD"]:
            return True
        elif password != "":
            st.error("Password incorrect. Please try again.")
            return False
        else:
            st.info("A password is required to use this application.")
            return False
    except KeyError:
        st.error("🔴 Critical Error: Application password is not configured. Please contact the administrator.")
        return False

# --- Main script execution ---
if check_password():
    run_the_app()
