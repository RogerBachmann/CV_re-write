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
import re
from xml.sax.saxutils import escape

# -------------------------------------
# 2. GEMINI API CONFIGURATION
# -------------------------------------
st.set_page_config(layout="wide", page_title="Swiss CV Enhancer")
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error("🔴 Critical Error: Cannot connect to the AI service. The GEMINI_API_KEY may be missing or invalid. Please contact the administrator.")
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
        st.error(f"Error reading file: {uploaded_file.name}. The file might be corrupted or in an unsupported format.")
    return ""

def robust_json_parser(raw_text_from_ai):
    """A more robust JSON parser that handles common AI errors."""
    try:
        clean_text = re.sub(r'^```json\s*|```\s*$', '', raw_text_from_ai.strip())
        start = clean_text.find('{')
        end = clean_text.rfind('}') + 1
        if start == -1 or end == 0:
            raise ValueError("JSON object not found in the AI response.")
        clean_json_text = clean_text[start:end]
        clean_json_text = re.sub(r',\s*([}\]])', r'\1', clean_json_text)
        return json.loads(clean_json_text)
    except (ValueError, json.JSONDecodeError) as e:
        st.error(f"🔴 Error: Could not parse the AI's response as valid JSON. Details: {e}")
        st.text_area("Raw output from AI (for debugging):", raw_text_from_ai, height=200)
        return None

def extract_raw_data(consolidated_text):
    """
    AI STEP 1: Purely extracts raw data from text into a JSON structure.
    This step does no rewriting and uses a simple, reliable prompt.
    """
    prompt = f"""
    You are a data extraction engine. Your sole purpose is to read the following text and extract all relevant information into a clean, valid JSON object. Do NOT rewrite, embellish, or change any of the text. Focus on complete and accurate extraction. Use British English for any location names if variants exist.

    **JSON Structure Requirements:**
    1.  `personal_info`: Extract "name", "job_title" (from the CV), "phone", "email", "city", "zip", "country", "linkedin_url".
    2.  `summary_paragraphs`: Extract any summary or "about me" paragraphs as a list of strings.
    3.  `languages`: Extract all languages and their proficiency levels into a list of objects, each with "language" and "level" keys.
    4.  `skills`: Extract all distinct skills into a simple list of strings.
    5.  `work_experience`: Extract EVERY job entry. Each must be an object with "company", "from_date", "to_date", "job_title", "responsibility", and "achievements" (as a list of strings).
    6.  `education`: Extract EVERY educational entry. Each must be an object with "degree", "graduation_date", "university", "university_location", "university_country".
    7.  `hobbies`: Extract all hobbies into a simple list of strings.

    If information for a key is not found, use an empty string "" or an empty list []. Your entire output must be ONLY the JSON object.

    CONSOLIDATED INPUT TEXT:
    ---
    {consolidated_text}
    ---
    """
    try:
        response = model.generate_content(prompt)
        if not response.parts:
            st.error("🔴 AI Extractor Error: The response was empty.")
            return None
        return robust_json_parser(response.text)
    except Exception as e:
        st.error(f"An unexpected error occurred during data extraction: {e}")
        return None

def rewrite_extracted_data(extracted_data, tone_selection):
    """
    AI STEP 2: Takes clean JSON and rewrites it using your non-negotiable expert prompt.
    """
    prompt = f"""
    You are a Tier-1 executive career coach and CV writer, specializing in crafting documents for senior-level candidates targeting the Swiss market. Your expertise is in transforming raw, informal career data into a polished, compelling, and strategically effective narrative.

    Your task is to analyze the provided CLEAN JSON DATA below. You must first synthesize all this information, then professionally rewrite the content according to the detailed rules, and finally return the data as a single, clean JSON object.

    CLEAN JSON DATA (FROM STEP 1):
    ---
    {json.dumps(extracted_data, indent=2)}
    ---

    **JSON Structure Requirements for FINAL OUTPUT (Strictly follow this for looping):**
    The root JSON object must contain these keys: "personal_info", "summary_paragraphs", "languages", "skills", "work_experience", "education", "hobbies".

    1.  `personal_info`: An object with keys "NAME", "JOB_TITLE", "phone", "email", "city", "zip", "country", "Linkedin".
    2.  `summary_paragraphs`: A list of strings, containing exactly two paragraphs.
    3.  `languages`: A list of objects, each with "language" and "level" keys.
    4.  `skills`: A simple list of strings.
    5.  `work_experience`: A list of objects. Each object represents a single job and MUST have these keys: "company", "from", "to", "title". Additionally it may have these keys: "responsibility", and "achievements". "achievements" MUST contain a list of strings.
    6.  `education`: A list of objects, each with "degree", "graduation", "university", "university_location", "university_country" keys.
    7.  `hobbies`: A simple list of strings.

    ---

    **Master Objective:** The final output must read like it was written by a human, Swiss career expert. It must be strategic, persuasive, and reflect the candidate as a high-impact individual in their field.

    **Advanced Rewriting and Content Generation Rules:**

    **1. Core Analysis & `JOB_TITLE` Determination:**
    - First, analyze all the text within the provided JSON. Identify if a potential future job description was included alongside the candidate's CV data.
    - **`JOB_TITLE`:** This is the future job title for the person.
        - If a job description seems present, derive the `JOB_TITLE` from it.
        - If not, create an executive-sounding future headline based on their most recent `job_title` (e.g., if they are an "Account Manager," the new `JOB_TITLE` could be "Commercial Expert" or "Key Account Director").
    - **`personal_info.NAME`:** Capitalize the person's name.

    **2. Tone and Language (CRITICAL):**
    - **Language:** Use British English spelling and grammar.
    - **Dynamic Tone Selection:** The user has selected the following tone: **'{tone_selection}'**. You MUST adapt your writing style accordingly.
        - 'Executive / Leadership': Use authoritative and strategic language.
        - 'Technical / Expert': Focus on deep domain knowledge and specific technologies.
        - 'Sales / Commercial': Use persuasive language focused on growth and revenue.

    **3. Professional Summary (`summary_paragraphs`):**
    - **Paragraph 1 (Strictly Two Sentences):** This paragraph must consist of exactly two complete sentences. DO NOT use headline fragments or '|' separators.
        - **Sentence 1:** Define the candidate's professional identity using the new `JOB_TITLE` (e.g., "Commercial Expert with 15 years of experience in the premium cosmetics sector.").
        - **Sentence 2:** State their single most impressive and quantifiable achievement from their recent career (e.g., "Most recently, drove regional growth by 18% through the implementation of a new sales training curriculum.").
        - **Constraint:** The entire paragraph must not exceed 310 characters (including spaces).
    - **Paragraph 2:** Write from the first-person ("I") perspective. Synthesize the candidate's core motivators and values. If no information is provided, create a strong, fitting paragraph based on their profile. **Strictly adhere to a maximum of 160 characters (including spaces).**

    **4. Work Experience (`work_experience`):**
    - Rename `job_title` to `title`, `from_date` to `from`, `to_date` to `to`.
    - **Responsibility:** Write 1-2 concise sentences defining the scope and core purpose of the role. Quantify it immediately if possible.
    - **Achievements:**
        - **Result-by-Action Framework:** Rewrite each bullet to follow: "I achieved [Result] by [action]."
        - **Quantification:** Use numbers from the input text. If none are present, create a strong, descriptive, non-quantified achievement. Do not invent numbers.
        - **Number of Bullet Points:** Generate up to 3 achievement bullet points per job.

    **5. Education:** Rename `graduation_date` to `graduation`.

    **6. Negative Constraints (What to AVOID AT ALL COSTS):**
    - **No Passive Voice:** Change "was responsible for" to "Managed," "Oversaw," etc.
    - **NO BUZZWORDS:** Strictly avoid: seasoned, results-driven, dynamic, motivated, proven track record, passionate, innovative, creative thinker, strategic thinker, go-getter, self-starter, team player, leader of change, strong communicator, influencer, people-oriented, cross-functional collaborator, change agent, highly accomplished, expert in. Demonstrate qualities, do not state them.

    **Final Instruction:** Your entire output MUST be a single, valid JSON object conforming to the final structure, and nothing else.
    """
    try:
        response = model.generate_content(prompt)
        if not response.parts:
            st.error("🔴 AI Rewriter Error: The response was empty.")
            return None
        return robust_json_parser(response.text)
    except Exception as e:
        st.error(f"An unexpected error occurred during data rewriting: {e}")
        return None

def generate_word_document(context):
    """Renders the final context dictionary into the Word template."""
    try:
        def escape_nested_dict(d):
            if isinstance(d, dict): return {k: escape_nested_dict(v) for k, v in d.items()}
            elif isinstance(d, list): return [escape_nested_dict(i) for i in d]
            elif isinstance(d, str): return escape(d)
            else: return d
        cleaned_context = escape_nested_dict(context)
        if not os.path.exists("CVTemplate_Python.docx"):
            st.error("🔴 Critical Error: The template file 'CVTemplate_Python.docx' was not found.")
            return None
        doc = DocxTemplate("CVTemplate_Python.docx")
        doc.render(cleaned_context)
        doc_buffer = io.BytesIO()
        doc.save(doc_buffer)
        doc_buffer.seek(0)
        return doc_buffer
    except Exception as e:
        st.error(f"Error generating the Word document: {e}. Check that your template keys match the data structure.")
    return None

# -------------------------------------
# 4. THE MAIN APPLICATION LOGIC
# -------------------------------------
def run_the_app():
    st.sidebar.success("✅ Logged in successfully!")
    st.title("🇨🇭 The Ultimate Swiss CV Enhancer")

    if 'cv_data' not in st.session_state: st.session_state.cv_data = None

    st.header("Step 1: Provide Your Information")
    col1, col2 = st.columns(2)
    with col1:
        uploaded_files = st.file_uploader("Upload documents (CV, job description, etc.)", type=["pdf", "docx"], accept_multiple_files=True)
    with col2:
        free_text_input = st.text_area("Paste additional text or notes here:", height=200)

    tone_selection = st.selectbox( "Select the Desired Tone:", ("Executive / Leadership", "Technical / Expert", "Sales / Commercial", "Project Management", "General Professional"))

    if st.button("🚀 Analyse, Rewrite & Fill Form", type="primary", use_container_width=True):
        all_texts = [free_text_input] if free_text_input else []
        if uploaded_files:
            for file in uploaded_files:
                text = extract_text_from_file(file)
                if text: all_texts.append(text)
        if not all_texts:
            st.warning("Please upload at least one file or provide some text.")
        else:
            consolidated_text = "\n\n--- DOCUMENT SEPARATOR ---\n\n".join(all_texts)
            with st.spinner("🤖 Step 1/2: Extracting raw data from documents..."):
                extracted_data = extract_raw_data(consolidated_text)
            if extracted_data:
                st.info("✅ Raw data extracted. Now applying expert rewriting rules...")
                with st.spinner(f"🤖 Step 2/2: Rewriting content for a '{tone_selection}' role..."):
                    rewritten_data = rewrite_extracted_data(extracted_data, tone_selection)
                    if rewritten_data:
                        st.session_state.cv_data = rewritten_data
                        st.success("✨ Success! The form is filled. Review and edit the content below.")
                        st.balloons()
                    else:
                        st.error("AI Rewriting Failed.")
            else:
                st.error("AI Extraction Failed.")

    if st.session_state.cv_data:
        st.header("Step 2: Review, Edit, and Generate")
        data = st.session_state.cv_data
        with st.form(key='cv_editor_form'):
            # This form directly edits values in session state for simplicity
            with st.expander("👤 Personal Information", expanded=True):
                p_info = data.get('personal_info', {})
                col1, col2 = st.columns(2)
                st.text_input("Full Name", p_info.get('NAME'), key="p_NAME")
                st.text_input("Target Job Title", p_info.get('JOB_TITLE'), key="p_JOB_TITLE")
                st.text_input("Email", p_info.get('email'), key="p_email")
                st.text_input("Phone", p_info.get('phone'), key="p_phone")
                st.text_input("City", p_info.get('city'), key="p_city")
                st.text_input("ZIP", p_info.get('zip'), key="p_zip")
                st.text_input("Country", p_info.get('country'), key="p_country")
                st.text_input("LinkedIn Profile URL", p_info.get('Linkedin'), key="p_Linkedin")

            with st.expander("📄 Professional Summary", expanded=True):
                summaries = data.get('summary_paragraphs', ['', ''])
                st.text_area("Summary Paragraph 1", summaries[0] if len(summaries) > 0 else "", height=100, key="summary_1", max_chars=310)
                st.text_area("Summary Paragraph 2 (first-person 'I')", summaries[1] if len(summaries) > 1 else "", height=80, key="summary_2", max_chars=160)

            with st.expander("💼 Work Experience", expanded=True):
                if 'work_experience' in data and data['work_experience']:
                    for i, job in enumerate(data['work_experience']):
                        st.markdown(f"--- \n**Job {i+1}**")
                        st.text_input("Job Title", job.get('title'), key=f"we_title_{i}")
                        st.text_input("Company", job.get('company'), key=f"we_company_{i}")
                        col1, col2 = st.columns(2)
                        col1.text_input("From Date", job.get('from'), key=f"we_from_{i}")
                        col2.text_input("To Date", job.get('to'), key=f"we_to_{i}")
                        st.text_area("Responsibility", job.get('responsibility', ''), key=f"we_resp_{i}", height=100)
                        st.text_area("Achievements (one per line)", "\n".join(job.get('achievements', [])), key=f"we_ach_{i}", height=120)

            with st.expander("🎓 Education & Qualifications", expanded=True):
                if 'education' in data and data['education']:
                    for i, edu in enumerate(data['education']):
                        st.markdown(f"--- \n**Qualification {i+1}**")
                        st.text_input("Degree/Qualification", edu.get('degree'), key=f"edu_degree_{i}")
                        st.text_input("Graduation Date", edu.get('graduation'), key=f"edu_graduation_{i}")
                        st.text_input("University/Institution", edu.get('university'), key=f"edu_university_{i}")
                        col1, col2 = st.columns(2)
                        col1.text_input("University Location", edu.get('university_location'), key=f"edu_location_{i}")
                        col2.text_input("University Country", edu.get('university_country'), key=f"edu_country_{i}")

            col1, col2, col3 = st.columns(3)
            with col1:
                with st.expander("🛠️ Skills"): st.text_area("Skills (comma separated)", ", ".join(data.get('skills', [])), key="skills")
            with col2:
                with st.expander("🌐 Languages"): st.text_area("Languages (Name: Level)", "\n".join([f"{l['language']}: {l['level']}" for l in data.get('languages', [])]), key="languages")
            with col3:
                with st.expander("🎨 Hobbies"): st.text_area("Hobbies (comma separated)", ", ".join(data.get('hobbies', [])), key="hobbies")

            submit_button = st.form_submit_button(label='📄 Generate Final Word Document', use_container_width=True)

        if submit_button:
            # CORRECTED: This block now builds the 'final_context' dictionary to EXACTLY match your Word template.
            final_context = {}
            
            # Unpack personal info fields to the top level for the template
            final_context['NAME'] = st.session_state.p_NAME
            final_context['JOB_TITLE'] = st.session_state.p_JOB_TITLE
            final_context['phone'] = st.session_state.p_phone
            final_context['email'] = st.session_state.p_email
            final_context['city'] = st.session_state.p_city
            final_context['zip'] = st.session_state.p_zip
            final_context['country'] = st.session_state.p_country
            final_context['Linkedin'] = st.session_state.p_Linkedin

            # Assign summary paragraphs to the specific keys the template expects
            final_context['summary_paragraph_1'] = st.session_state.summary_1
            final_context['summary_paragraph_2'] = st.session_state.summary_2
            
            # Reconstruct lists for loops from the form fields
            final_context['work_experience'] = [{'title': st.session_state[f'we_title_{i}'], 'company': st.session_state[f'we_company_{i}'], 'from': st.session_state[f'we_from_{i}'], 'to': st.session_state[f'we_to_{i}'], 'responsibility': st.session_state[f'we_resp_{i}'], 'achievements': [line.strip() for line in st.session_state[f'we_ach_{i}'].split('\n') if line.strip()]} for i, _ in enumerate(data['work_experience'])]
            final_context['education'] = [{'degree': st.session_state[f'edu_degree_{i}'], 'graduation': st.session_state[f'edu_graduation_{i}'], 'university': st.session_state[f'edu_university_{i}'], 'university_location': st.session_state[f'edu_location_{i}'], 'university_country': st.session_state[f'edu_country_{i}']} for i, _ in enumerate(data.get('education', []))]
            final_context['skills'] = [s.strip() for s in st.session_state.skills.split(',') if s.strip()]
            final_context['hobbies'] = [h.strip() for h in st.session_state.hobbies.split(',') if h.strip()]
            final_context['languages'] = [{'language': line.partition(':')[0].strip(), 'level': line.partition(':')[2].strip()} for line in st.session_state.languages.split('\n') if ':' in line]
            
            with st.spinner("Creating your polished Word document..."):
                doc_buffer = generate_word_document(final_context)
                if doc_buffer:
                    st.success("✅ Document Generated!")
                    st.download_button(label="📥 Download Your Enhanced CV", data=doc_buffer, file_name=f"Enhanced_CV_{final_context.get('NAME', 'CV')}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)

# -------------------------------------
# 5. PASSWORD CHECK
# -------------------------------------
def check_password():
    """Returns `True` if the user entered the correct password."""
    try:
        if st.session_state.get("password_correct", False):
            return True
        st.title("🔐 Secure Access")
        password = st.text_input("Please enter the password to access the tool:", type="password", key="password_input")
        correct_password = st.secrets.get("APP_PASSWORD")
        if not correct_password:
             st.error("🔴 Critical Error: Application password is not configured in st.secrets.")
             return False
        if password == correct_password:
            st.session_state.password_correct = True
            st.rerun()
        elif password:
            st.error("Password incorrect. Please try again.")
        else:
            st.info("A password is required to use this application.")
        return False
    except Exception as e:
        st.error(f"🔴 An unexpected error occurred in the password check function: {e}")
        return False

# --- Main script execution ---
if check_password():
    run_the_app()
