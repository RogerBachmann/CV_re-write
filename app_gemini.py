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
from xml.sax.saxutils import escape

# -------------------------------------
# 2. GEMINI API CONFIGURATION
# -------------------------------------
st.set_page_config(layout="wide")
try:
    # Use st.secrets for deployment. This is the correct way for Streamlit Cloud.
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
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
    """The main AI function that parses, rewrites, and returns structured JSON for loops."""
    prompt = f"""
    You are a Tier-1 executive career coach and CV writer... (shortened for brevity)

    **JSON Structure Requirements (Strictly follow this for looping):**
    The root JSON object must contain these keys: "personal_info", "summary_paragraphs", "languages", "skills", "work_experience", "education", "hobbies".

    1.  `personal_info`: An object with keys "NAME", "JOB_TITLE", "phone", "email", "city", "zip", "Linkedin".
    2.  `summary_paragraphs`: A list of strings, containing exactly two paragraphs.
    3.  `languages`: A list of objects, each with "language" and "level" keys.
    4.  `skills`: A simple list of strings.
    5.  `work_experience`: A list of objects. Each object represents a single job and MUST have these keys: "company", "from", "to", "title", "responsibility", and "achievements". 
        -- MODIFICATION: Changed "job_title" to "title" to match your template --
        - The "achievements" key MUST contain a list of strings (can be empty).
    6.  `education`: A list of objects, each with "degree", "graduation", "university", "university_location", "university_country" keys.
    7.  `hobbies`: A simple list of strings.

    ---
    (The rest of your detailed rewriting rules remain the same)
    ---

    CONSOLIDATED INPUT TEXT:
    ---
    {consolidated_text}
    ---
    """
    try:
        response = model.generate_content(prompt)
        if not response.parts:
            st.error("🔴 The AI response was empty. This can happen if the input triggers a content safety filter.")
            return None
        raw_text_from_ai = response.text
        try:
            start = raw_text_from_ai.find('{')
            end = raw_text_from_ai.rfind('}') + 1
            if start == -1 or end == 0: raise ValueError("A valid JSON object was not found in the AI's response.")
            clean_json_text = raw_text_from_ai[start:end]
            return json.loads(clean_json_text)
        except (ValueError, json.JSONDecodeError) as e:
            st.error(f"🔴 Error: Could not parse the AI's response as valid JSON. Details: {e}")
            st.text_area("Raw output from AI (for debugging):", raw_text_from_ai, height=200)
            return None
    except Exception as e:
        st.error(f"An unexpected error occurred with the Gemini API: {e}")
        return None

def generate_word_document(context):
    """Renders the final context dictionary into the Word template, escaping special characters."""
    try:
        def escape_nested_dict(d):
            if isinstance(d, dict):
                return {k: escape_nested_dict(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [escape_nested_dict(i) for i in d]
            elif isinstance(d, str):
                return escape(d)
            else:
                return d

        cleaned_context = escape_nested_dict(context)

        doc = DocxTemplate("CVTemplate_Python.docx")
        doc.render(cleaned_context)
        
        doc_buffer = io.BytesIO()
        doc.save(doc_buffer)
        doc_buffer.seek(0)
        return doc_buffer
    except Exception as e:
        st.error(f"Error generating Word doc: {e}. Ensure your template uses the correct loop syntax.")
    return None

# -------------------------------------
# 4. THE MAIN APPLICATION LOGIC
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
                st.session_state.cv_data = parse_and_rewrite_cv(consolidated_text, tone_selection)

    if st.session_state.cv_data:
        st.success("✅ Success! The form below is now filled. Review the content before generating the document.")
        st.header("Step 2: Review, Edit, and Generate Final Document")

        data = st.session_state.cv_data
        
        with st.form(key='cv_template_form'):
            with st.expander("Personal Information", expanded=True):
                p_info = data.get('personal_info', {})
                p_info['NAME'] = st.text_input("Name", value=p_info.get('NAME', ''))
                p_info['JOB_TITLE'] = st.text_input("Overall Job Title", value=p_info.get('JOB_TITLE', ''))
                # Other personal fields...

            with st.expander("Professional Summary", expanded=True):
                summary_paras = data.get('summary_paragraphs', ['',''])
                summary_paras[0] = st.text_area("Summary Paragraph 1", value=summary_paras[0], height=120)
                summary_paras[1] = st.text_area("Summary Paragraph 2", value=summary_paras[1], height=80)

            with st.expander("Work Experience", expanded=True):
                work_experience = data.get('work_experience', [])
                for i, exp in enumerate(work_experience):
                    st.subheader(f"Work Experience #{i+1}")
                    exp['company'] = st.text_input("Company", value=exp.get('company', ''), key=f"c_{i}")
                    # MODIFICATION: Changed 'job_title' to 'title' to match your template
                    exp['title'] = st.text_input("Job Title", value=exp.get('title', ''), key=f"t_{i}")
                    col1, col2 = st.columns(2)
                    exp['from'] = col1.text_input("Start Date", value=exp.get('from', ''), key=f"from_{i}")
                    exp['to'] = col2.text_input("End Date", value=exp.get('to', ''), key=f"to_{i}")
                    exp['responsibility'] = st.text_area("Responsibility", value=exp.get('responsibility', ''), height=80, key=f"resp_{i}")
                    achievements_text = "\n".join(exp.get('achievements', []))
                    updated_achievements = st.text_area("Achievements (one per line)", value=achievements_text, height=100, key=f"ach_{i}")
                    exp['achievements'] = [line.strip() for line in updated_achievements.split('\n') if line.strip()]
                    st.markdown("---")
            
            # Additional expanders for Education, Skills, etc. can be added here if needed for editing.

            submit_button = st.form_submit_button(label='📄 Generate Final Word Document')

        if submit_button:
            # The context building is now very simple. We just pass the entire 'data' dictionary.
            final_context = data
            with st.spinner("Creating your polished Word document..."):
                doc_buffer = generate_word_document(final_context)
                if doc_buffer:
                    st.success("🎉 Your CV has been generated!")
                    st.download_button(
                        label="⬇️ Download Final CV",
                        data=doc_buffer,
                        file_name=f"CV_{data.get('personal_info',{}).get('NAME','candidate').replace(' ','_')}.docx"
                    )

# -------------------------------------
# 5. PASSWORD CHECK
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
