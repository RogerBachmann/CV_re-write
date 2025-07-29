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
    """AI STEP 1: Purely extracts raw data from text into a JSON structure."""
    prompt = f"""
    You are a data extraction engine. Your sole purpose is to read the following text and extract all relevant information into a clean, valid JSON object. Do NOT rewrite, embellish, or change any of the text. Focus on complete and accurate extraction. Use British English for any location names if variants exist.

    **JSON Structure Requirements:**
    1.  `personal_info`: Extract "name", "job_title" (from the CV), "phone", "email", "city", "zip", "country", "linkedin_url".
    2.  `summary_paragraphs`: Extract any summary or "about me" paragraphs as a list of strings.
    3.  `languages`: Extract all languages and their proficiency levels into a list of objects, each with "language" and "level" keys.
    4.  `skills`: Extract all distinct skills as a list of individual string keywords.
    5.  `work_experience`: Extract EVERY job entry. Each must be an object with "company", "from_date", "to_date", "job_title", "responsibility", and "achievements" (as a list of strings).
    6.  `education`: Extract EVERY educational entry. Each must be an object with "degree", "graduation_date", "university", "university_location", "university_country".
    7.  `hobbies`: Extract all hobbies as a list of individual string keywords.

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
    AI STEP 2: Takes clean JSON and rewrites it using the REFINED expert prompt.
    """
    # REFINED PROMPT with anti-exaggeration rules.
    prompt = f"""
    You are a meticulous and precise professional CV editor for the Swiss market. Your task is to refine the provided raw JSON data into a polished, professional, and factual narrative.

    CLEAN JSON DATA (FROM STEP 1):
    ---
    {json.dumps(extracted_data, indent=2)}
    ---

    **JSON Structure Requirements for FINAL OUTPUT (Strictly follow this):**
    The root JSON object must contain these keys: "personal_info", "summary_paragraphs", "languages", "skills", "work_experience", "education", "hobbies". All keys must be present.
    - `personal_info`: Object with keys "NAME", "JOB_TITLE", "phone", "email", "city", "zip", "country", "Linkedin".
    - `summary_paragraphs`: List of two strings.
    - `languages`: List of objects, each with "language" and "level".
    - `skills`: List of individual skill keywords (strings).
    - `work_experience`: List of objects, each with "company", "from", "to", "title", "responsibility", "achievements" (list of strings).
    - `education`: List of objects, each with "degree", "graduation", "university", "university_location", "university_country".
    - `hobbies`: List of individual hobby keywords (strings).

    ---

    **Advanced Rewriting and Content Generation Rules:**

    **1. Core Analysis & `JOB_TITLE` Determination:**
    - Analyze the input to identify if a future job description is present.
    - **`JOB_TITLE`:** If a job description exists, derive the `JOB_TITLE` from it. Otherwise, create a professional, grounded future headline based on their most recent role (e.g., "Account Manager" becomes "Commercial Specialist" or "Key Account Manager," not "Sales Legend").
    - **`personal_info.NAME`:** Capitalize the person's name.

    **2. Tone and Language (CRITICAL):**
    - **Language:** Use British English.
    - **Dynamic Tone Selection:** Adapt your writing style for the selected tone: **'{tone_selection}'**.
    - **Constraint on Exaggeration:** This is a critical rule. Stick closely to the facts provided. Do not invent metrics, outcomes, or unsupported superlatives. The goal is professional refinement, not marketing hyperbole. The tone should be confident but grounded and factual.

    **3. Professional Summary (`summary_paragraphs`):**
    - **Paragraph 1 (Strictly Two Sentences, max 310 chars):**
        - Sentence 1: Define the professional identity using the new `JOB_TITLE`.
        - Sentence 2: State their most impressive, verifiable achievement from their career.
    - **Paragraph 2 (First-person "I", max 160 chars):**
        - Synthesize core motivators and professional values. If none are provided, create a fitting, professional paragraph based on their profile.

    **4. Work Experience (`work_experience`):**
    - Rename `job_title` to `title`, `from_date` to `from`, `to_date` to `to`.
    - **Responsibility:** Write 1-2 concise, factual sentences defining the role's scope.
    - **Achievements:**
        - **Framework:** "I achieved [Result] by [action]."
        - **Quantification:** Use numbers from the input text only. If none are present, describe the outcome professionally without exaggeration (e.g., instead of 'drove massive growth,' write 'contributed to sales growth initiatives'). Generate up to 3 achievements per job.

    **5. Skills & Hobbies:**
    - Ensure `skills` and `hobbies` are returned as clean lists of individual keywords or short phrases, not long sentences.

    **6. Education:** Rename `graduation_date` to `graduation`.

    **7. Negative Constraints (AVOID AT ALL COSTS):**
    - **No Passive Voice.**
    - **NO BUZZWORDS:** Strictly avoid the forbidden list (seasoned, results-driven, dynamic, etc.).

    **Final Instruction:** Your entire output MUST be a single, valid JSON object conforming to the final structure.
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
        st.error(f"Error generating the Word document: {e}. Ensure your Word template is not corrupt and its syntax is correct.")
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
                    else: st.error("AI Rewriting Failed.")
            else: st.error("AI Extraction Failed.")

    if st.session_state.cv_data:
        st.header("Step 2: Review, Edit, and Generate")
        data = st.session_state.cv_data
        with st.form(key='cv_editor_form'):
            with st.expander("👤 Personal Information", expanded=True):
                p_info = data.get('personal_info', {})
                # Form fields directly write to session_state keys for reconstruction
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
                        st.text_input(f"Job Title {i+1}", job.get('title'), key=f"we_title_{i}")
                        st.text_input(f"Company {i+1}", job.get('company'), key=f"we_company_{i}")
                        st.text_area(f"Responsibility {i+1}", job.get('responsibility', ''), key=f"we_resp_{i}", height=100)
                        st.text_area(f"Achievements {i+1}", "\n".join(job.get('achievements', [])), key=f"we_ach_{i}", height=120)

            # FIXED: Skills and Hobbies UI
            with st.expander("🛠️ Skills, Languages & Hobbies"):
                col1, col2 = st.columns(2)
                col1.text_area("Skills (one per line)", "\n".join(data.get('skills', [])), key="skills", height=200)
                col2.text_area("Languages (Name: Level)", "\n".join([f"{l['language']}: {l['level']}" for l in data.get('languages', [])]), key="languages", height=200)
                st.text_area("Hobbies & Extracurricular (one per line)", "\n".join(data.get('hobbies', [])), key="hobbies", height=150)
            
            submit_button = st.form_submit_button(label='📄 Generate Final Word Document', use_container_width=True)

        if submit_button:
            # Build the context dictionary EXACTLY as the Word template expects
            final_context = {}
            p_info_data = data.get('personal_info', {})
            final_context['NAME'] = st.session_state.get('p_NAME', p_info_data.get('NAME'))
            final_context['JOB_TITLE'] = st.session_state.get('p_JOB_TITLE', p_info_data.get('JOB_TITLE'))
            final_context['phone'] = st.session_state.get('p_phone', p_info_data.get('phone'))
            final_context['email'] = st.session_state.get('p_email', p_info_data.get('email'))
            final_context['city'] = st.session_state.get('p_city', p_info_data.get('city'))
            final_context['zip'] = st.session_state.get('p_zip', p_info_data.get('zip'))
            final_context['country'] = st.session_state.get('p_country', p_info_data.get('country'))
            final_context['Linkedin'] = st.session_state.get('p_Linkedin', p_info_data.get('Linkedin'))
            final_context['summary_paragraph_1'] = st.session_state.summary_1
            final_context['summary_paragraph_2'] = st.session_state.summary_2
            final_context['work_experience'] = [{'title': st.session_state[f'we_title_{i}'], 'company': st.session_state[f'we_company_{i}'], 'responsibility': st.session_state[f'we_resp_{i}'], 'achievements': [line.strip() for line in st.session_state[f'we_ach_{i}'].split('\n') if line.strip()]} for i, _ in enumerate(data['work_experience'])]
            final_context['education'] = data.get('education', []) # Education is not editable in the form, so pass it directly
            # FIXED: Reconstruct from one-per-line text areas
            final_context['skills'] = [s.strip() for s in st.session_state.skills.split('\n') if s.strip()]
            final_context['hobbies'] = [h.strip() for h in st.session_state.hobbies.split('\n') if h.strip()]
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
