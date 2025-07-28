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
    """The main AI function that parses, rewrites, and returns structured JSON for loops."""
    # This is the final, most advanced prompt incorporating all your rules.
    prompt = f"""
    You are a Tier-1 executive career coach and CV writer, specializing in crafting documents for senior-level candidates targeting the Swiss, German, and Austrian markets. Your expertise is in transforming raw, informal career data into a polished, compelling, and strategically effective narrative.

    Your task is to analyze the CONSOLIDATED INPUT TEXT provided below. You must first synthesize all this information, then professionally rewrite the content according to the detailed rules below, and finally return the data as a single, clean JSON object.

    **JSON Structure Requirements (Strictly follow this for looping):**
    The root JSON object must contain these keys: "personal_info", "summary_paragraphs", "languages", "skills", "work_experience", "education", "hobbies".

    1.  `personal_info`: An object with keys "NAME", "JOB_TITLE", "phone", "email", "city", "zip", "Linkedin".
    2.  `summary_paragraphs`: A list of strings, containing exactly two paragraphs.
    3.  `languages`: A list of objects, each with "language" and "level" keys.
    4.  `skills`: A simple list of strings.
    5.  `work_experience`: A list of objects. Each object represents a single job and MUST have these keys: "company", "from", "to", "title", "responsibility", and "achievements".
        - The "achievements" key MUST contain a list of strings (can be empty).
    6.  `education`: A list of objects, each with "degree", "graduation", "university", "university_location", "university_country" keys.
    7.  `hobbies`: A simple list of strings.

    ---

    **Master Objective:** The final output must read like it was written by a human expert. It must be strategic, persuasive, and reflect the candidate as a high-impact individual in their field.

    **Advanced Rewriting and Content Generation Rules:**

    **1. Tone and Language (CRITICAL):**
    - **Language:** Use British English.
    - **Contextual Analysis:** If a job description is included, tailor the CV's language and skills towards that job.
    - **Dynamic Tone Selection:** The user has selected the following tone: **'{tone_selection}'**. You MUST adapt your writing style accordingly.
        - 'Executive / Leadership': Use authoritative and strategic language.
        - 'Technical / Expert': Focus on deep domain knowledge and specific technologies.
        - 'Sales / Commercial': Use persuasive language focused on growth and revenue.

    **2. Professional Summary (`summary_paragraphs`):**
    - **Paragraph 1 (Strictly Two Sentences):** This paragraph must consist of exactly two complete sentences. DO NOT use headline fragments or '|' separators.
        - **Sentence 1:** Define the candidate's professional identity (e.g., "Commercial Leader with 15 years of experience in the premium cosmetics sector.").
        - **Sentence 2:** State their single most impressive and quantifiable achievement from their recent career (e.g., "Most recently, drove regional growth by 18% through the implementation of a new sales training curriculum.").
        - **The entire paragraph must not exceed 310 characters (including spaces).**
    - **Paragraph 2:** Write from the first-person ("I") perspective. Synthesize the candidate's core motivators and values. If no information is provided, create a strong, fitting paragraph based on their profile. **Strictly adhere to a maximum of 160 characters (including spaces).**

    **3. Work Experience (`work_experience`):**
    - **Responsibility:** Write 1-2 concise sentences defining the scope and core purpose of the role. Quantify it immediately if possible.
    - **Achievements:**
        - **Result-by-Action Framework:** "I achieved [Result] by [action]."
        - **Quantification:** Use numbers from the input text. If none are present, create a strong, descriptive, non-quantified achievement. Do not invent numbers.
        - **Number of Bullet Points:** Generate up to 3 achievement bullet points per job based on the input.

    **4. Negative Constraints (What to AVOID AT ALL COSTS):**
    - **No Passive Voice:** Change "was responsible for" to "Managed," "Oversaw," etc.
    - **NO BUZZWORDS:** Strictly avoid: seasoned, results-driven, dynamic, motivated, proven track record, passionate, innovative, creative thinker, strategic thinker, go-getter, self-starter, team player, leader of change, strong communicator, influencer, people-oriented, cross-functional collaborator, change agent, highly accomplished, expert in. Demonstrate qualities, do not state them.

    **Final Instruction:** If any information for a field is not found, use an empty string "" or an empty list []. Your entire output MUST be a single, valid JSON object and nothing else.

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
            # --- THIS IS THE FULL, COMPLETE, AND CORRECTED FORM ---
            with st.expander("Personal Information", expanded=True):
                p_info = data.get('personal_info', {})
                p_info['NAME'] = st.text_input("Name", value=p_info.get('NAME', ''))
                p_info['JOB_TITLE'] = st.text_input("Overall Job Title", value=p_info.get('JOB_TITLE', ''))
                p_info['phone'] = st.text_input("Phone", value=p_info.get('phone', ''))
                p_info['email'] = st.text_input("Email", value=p_info.get('email', ''))
                p_info['city'] = st.text_input("City", value=p_info.get('city', ''))
                p_info['zip'] = st.text_input("ZIP Code", value=p_info.get('zip', ''))
                p_info['Linkedin'] = st.text_input("LinkedIn URL", value=p_info.get('Linkedin', ''))
            
            with st.expander("Professional Summary", expanded=True):
                summary_paras = data.get('summary_paragraphs', [])
                while len(summary_paras) < 2: summary_paras.append('')
                summary_paras[0] = st.text_area("Summary Paragraph 1", value=summary_paras[0], height=120)
                summary_paras[1] = st.text_area("Summary Paragraph 2", value=summary_paras[1], height=80)

            with st.expander("Work Experience", expanded=True):
                work_experience = data.get('work_experience', [])
                for i, exp in enumerate(work_experience):
                    st.subheader(f"Work Experience #{i+1}")
                    exp['company'] = st.text_input("Company", value=exp.get('company', ''), key=f"c_{i}")
                    exp['title'] = st.text_input("Job Title", value=exp.get('title', ''), key=f"t_{i}")
                    col1, col2 = st.columns(2)
                    exp['from'] = col1.text_input("Start Date", value=exp.get('from', ''), key=f"from_{i}")
                    exp['to'] = col2.text_input("End Date", value=exp.get('to', ''), key=f"to_{i}")
                    exp['responsibility'] = st.text_area("Responsibility", value=exp.get('responsibility', ''), height=80, key=f"resp_{i}")
                    achievements_text = "\n".join(exp.get('achievements', []))
                    updated_achievements = st.text_area("Achievements (one per line)", value=achievements_text, height=100, key=f"ach_{i}")
                    exp['achievements'] = [line.strip() for line in updated_achievements.split('\n') if line.strip()]
                    st.markdown("---")

            with st.expander("Education & Qualifications"):
                education = data.get('education', [])
                while len(education) < 6: education.append({})
                for i, edu in enumerate(education[:6]):
                    st.subheader(f"Education #{i+1}")
                    edu['degree'] = st.text_input("Degree", value=edu.get('degree',''), key=f"deg_{i}")
                    edu['graduation'] = st.text_input("Graduation Year", value=edu.get('graduation',''), key=f"grad_{i}")
                    edu['university'] = st.text_input("University", value=edu.get('university',''), key=f"uni_{i}")
                    c1,c2 = st.columns(2)
                    edu['university_location'] = c1.text_input("Location", value=edu.get('university_location',''), key=f"uniloc_{i}")
                    edu['university_country'] = c2.text_input("Country", value=edu.get('university_country',''), key=f"unicoun_{i}")
            
            col1, col2 = st.columns(2)
            with col1:
                with st.expander("Skills"):
                    skills = data.get('skills', [])
                    while len(skills) < 6: skills.append('')
                    for i in range(6): skills[i] = st.text_input(f"Skill {i+1}", value=skills[i], key=f"skill_{i}")
            with col2:
                with st.expander("Languages"):
                    languages = data.get('languages', [])
                    while len(languages) < 6: languages.append({'language':'', 'level':''})
                    for i in range(6):
                        lang_obj = languages[i]
                        c1, c2 = st.columns(2)
                        lang_obj['language'] = c1.text_input(f"Language {i+1}", value=lang_obj.get('language',''), key=f"lang_{i}")
                        lang_obj['level'] = c2.text_input(f"Level {i+1}", value=lang_obj.get('level',''), key=f"level_{i}")

            with st.expander("Hobbies & Extracurricular"):
                hobbies = data.get('hobbies', [])
                while len(hobbies) < 6: hobbies.append('')
                for i in range(6): hobbies[i] = st.text_input(f"Hobby {i+1}", value=hobbies[i], key=f"hobby_{i}")

            submit_button = st.form_submit_button(label='📄 Generate Final Word Document')

        if submit_button:
            # This logic builds the final context correctly
            final_context = {}
            
            # Use .update() to flatten the personal_info into the main context
            final_context.update(data.get('personal_info', {}))
            
            # Add the other lists directly, applying slicing to enforce limits
            final_context['summary_paragraphs'] = data.get('summary_paragraphs', [])
            final_context['skills'] = data.get('skills', [])[:6]
            final_context['hobbies'] = data.get('hobbies', [])[:6]
            final_context['languages'] = data.get('languages', [])[:6]
            final_context['education'] = data.get('education', [])[:6]
            final_context['work_experience'] = data.get('work_experience', [])[:15]
            
            with st.spinner("Creating your polished Word document..."):
                doc_buffer = generate_word_document(final_context)
                if doc_buffer:
                    st.success("🎉 Your CV has been generated!")
                    st.download_button(
                        label="⬇️ Download Final CV",
                        data=doc_buffer,
                        file_name=f"CV_{final_context.get('NAME','candidate').replace(' ','_')}.docx"
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
