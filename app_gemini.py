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
# NEW: Import the XML escaping utility
from xml.sax.saxutils import escape

# -------------------------------------
# 2. GEMINI API CONFIGURATION
# (This section is unchanged)
# -------------------------------------
st.set_page_config(layout="wide")
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error("🔴 Critical Error: Cannot connect to AI service. Please contact the administrator.")
    st.stop()

# -------------------------------------
# 3. HELPER FUNCTIONS
# -------------------------------------
# (The first two helper functions are unchanged)
def extract_text_from_file(uploaded_file):
    # ... (no changes here)
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
    # ... (no changes to the prompt or this function)
    prompt = f"""
    You are a Tier-1 executive career coach... 
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
    """
    MODIFIED: This function now uses a helper to clean the context data before rendering.
    """
    try:
        # Create a new, cleaned context dictionary
        cleaned_context = {}
        for key, value in context.items():
            if isinstance(value, str):
                # If the value is a string, escape it
                cleaned_context[key] = escape(value)
            else:
                # Otherwise, keep it as is (for lists, etc.)
                cleaned_context[key] = value

        doc = DocxTemplate("CVTemplate_Python.docx")
        # Use the cleaned_context to render the document
        doc.render(cleaned_context)
        
        doc_buffer = io.BytesIO()
        doc.save(doc_buffer)
        doc_buffer.seek(0)
        return doc_buffer
    except Exception as e:
        st.error(f"Error generating Word doc: {e}. Check 'CVTemplate_Python.docx' exists and all placeholders match the form.")
    return None

# -------------------------------------
# 4. THE MAIN APPLICATION LOGIC
# (This entire section is unchanged)
# -------------------------------------
def run_the_app():
    # ... (no changes here)
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
            # This is where all the st.expander and st.text_input form fields go
            # ... (no changes to the form itself)
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
            # This is where we build the final context dictionary. The logic is the same.
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
            for i, hobby in enumerate(data.get('hobbies', [])):
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
# (This section is unchanged)
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
