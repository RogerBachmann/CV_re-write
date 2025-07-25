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
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.error("🔴 Error: GEMINI_API_KEY not found. Please set it up first.")
        st.stop()
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    st.sidebar.success("✅ Gemini API Key Loaded")
except Exception as e:
    st.error(f"🔴 Error configuring Gemini API: {e}")
    st.stop()

# -------------------------------------
# 3. HELPER FUNCTIONS
# -------------------------------------

def extract_text_from_file(uploaded_file):
    # Unchanged
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

def parse_and_rewrite_cv(consolidated_text):
    """
    The main AI function. It now takes a consolidated block of text from multiple sources.
    """
    prompt = f"""
    You are an expert CV analyst and data extractor. Your task is to parse the CONSOLIDATED INPUT TEXT provided below, which may contain information from multiple documents (like a CV, a cover letter, and notes). Professionally rewrite the content in a senior, executive tone, and return the data as a single, clean JSON object that matches a specific template structure.

    **JSON Structure Requirements:**
    The root JSON object must contain these keys: "personal_info", "summary_paragraphs", "languages", "skills", "work_experience", "education", "hobbies".

    1.  `personal_info`: An object with keys "NAME", "JOB_TITLE", "phone", "email", "city", "zip", "Linkedin".
    2.  `summary_paragraphs`: A list of strings, containing exactly two paragraphs for the summary.
    3.  `languages`: A list of objects, each with "language" and "level". Provide up to 3.
    4.  `skills`: A list of strings for skills. Provide up to 3.
    5.  `work_experience`: A list of objects. Each object must have keys: "company", "from", "to", "job_title", "responsibility", and "achievements".
        - `achievements` MUST be a list of strings, containing exactly 3 achievement points.
    6.  `education`: A list of objects, each with "degree", "graduation", "university", "university_location", "university_country". Provide up to 2.
    7.  `hobbies`: A list of strings for hobbies. Provide up to 3.

    **Rewriting Rules:**
    - Synthesize information from all parts of the input to create the best possible profile.
    - Rewrite job descriptions to be achievement-focused using the STAR method.
    - Quantify scope and impact wherever possible.
    - Use a direct, precise, and senior tone in British English.
    - If information for any field is not found, use an empty string "" or an empty list [].
    - Your entire output MUST be a single, valid JSON object and nothing else.

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
    # Unchanged
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
# 4. STREAMLIT USER INTERFACE
# -------------------------------------

st.title("🇨🇭 The Ultimate CV Information Hub & Generator")

# Initialize session state
if 'cv_data' not in st.session_state:
    st.session_state.cv_data = None

# --- STEP 1: CONSOLIDATE ALL INPUTS ---
st.header("Step 1: Consolidate All Information")

# NEW: Multi-file uploader
uploaded_files = st.file_uploader(
    "Upload relevant documents (CV, cover letter, job description, etc.)",
    type=["pdf", "docx"],
    accept_multiple_files=True
)

# NEW: Free-text field for notes
free_text_input = st.text_area("Paste any additional notes, text, or ideas here:", height=150)

if st.button("🚀 Analyze All Info & Fill Form"):
    # NEW: Consolidation Logic
    all_texts = []
    
    # Extract text from all uploaded files
    if uploaded_files:
        for file in uploaded_files:
            st.write(f"Reading file: `{file.name}`...")
            all_texts.append(extract_text_from_file(file))
            
    # Add the free-text input
    if free_text_input:
        all_texts.append(free_text_input)

    if not all_texts:
        st.warning("Please upload at least one file or provide some text.")
    else:
        # Join everything into one master string
        consolidated_text = "\n\n--- DOCUMENT SEPARATOR ---\n\n".join(all_texts)
        
        with st.spinner("🤖 Gemini is synthesizing all info, rewriting, and structuring the CV..."):
            st.session_state.cv_data = parse_and_rewrite_cv(consolidated_text)

# --- STEP 2: REVIEW & GENERATE ---
if st.session_state.cv_data:
    st.success("✅ Success! The form below is now filled based on all provided info. Review before generating.")
    st.header("Step 2: Review, Edit, and Generate Final Document")

    data = st.session_state.cv_data
    
    with st.form(key='cv_template_form'):
        # This entire form section is the same as the previous robust version
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
            for i, exp in enumerate(work_experience):
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
                while len(skills) < 3: skills.append('')
                for i in range(3): skills[i] = st.text_input(f"Skill {i+1}", value=skills[i], key=f"skill_{i}")
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
            while len(education) < 2: education.append({})
            for i, edu in enumerate(education):
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
        # The logic to build the final context dictionary is unchanged
        final_context = {}
        final_context.update(data.get('personal_info', {}))
        summary_paras = data.get('summary_paragraphs', ['',''])
        final_context['summary_paragraph_1'] = summary_paras[0]
        final_context['summary_paragraph_2'] = summary_paras[1]
        for i, exp in enumerate(data.get('work_experience', [])):
            final_context[f'company_{i+1}'] = exp.get('company')
            final_context[f'from_{i+1}'] = exp.get('from')
            final_context[f'to_{i+1}'] = exp.get('to')
            final_context[f'job_title_{i+1}'] = exp.get('job_title')
            final_context[f'responsibility_{i+1}'] = exp.get('responsibility')
            for j, ach in enumerate(exp.get('achievements', [])):
                final_context[f'achievement_job_{i+1}_{j+1}'] = ach
        for i, lang in enumerate(data.get('languages', [])):
            final_context[f'language_{i+1}'] = lang.get('language')
            final_context[f'level_{i+1}'] = lang.get('level')
        for i, skill in enumerate(data.get('skills', [])):
            final_context[f'skill_{i+1}'] = skill
        for i, edu in enumerate(data.get('education', [])):
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
