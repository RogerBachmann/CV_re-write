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
import re

# -------------------------------------
# 2. GEMINI API CONFIGURATION
# -------------------------------------
st.set_page_config(layout="wide", page_title="Swiss CV Enhancer")
try:
    # Use st.secrets for secure API key storage in Streamlit Cloud
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
            # Using pdfplumber to handle PDFs
            with pdfplumber.open(uploaded_file) as pdf:
                return "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            # Using python-docx to handle DOCX
            doc = Document(uploaded_file)
            return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        st.error(f"Error reading file: {uploaded_file.name}. The file might be corrupted or in an unsupported format.")
    return ""

def robust_json_parser(raw_text_from_ai):
    """
    A more robust JSON parser that handles common AI errors like code block fences
    and illegal trailing commas.
    """
    try:
        # Clean the text by removing markdown code block fences (```json ... ```)
        clean_text = re.sub(r'^```json\s*|```\s*$', '', raw_text_from_ai.strip())

        # Attempt to find the main JSON object
        start = clean_text.find('{')
        end = clean_text.rfind('}') + 1
        if start == -1 or end == 0:
            raise ValueError("JSON object not found in the AI response.")

        clean_json_text = clean_text[start:end]

        # FIX: Specifically remove illegal trailing commas from objects and arrays
        # This regex finds a comma, followed by optional whitespace, right before a closing brace '}' or bracket ']'
        clean_json_text = re.sub(r',\s*([}\]])', r'\1', clean_json_text)

        return json.loads(clean_json_text)
    except (ValueError, json.JSONDecodeError) as e:
        st.error(f"🔴 Error: Could not parse the AI's response as valid JSON. Details: {e}")
        st.text_area("Raw output from AI (for debugging):", raw_text_from_ai, height=200)
        return None

def extract_raw_data(consolidated_text):
    """AI Step 1: Purely extracts data from text into a JSON structure. No rewriting."""
    # This is the stable, focused extraction prompt.
    prompt = f"""
    You are a data extraction engine. Your sole purpose is to read the following text and extract all relevant information into a clean, valid JSON object. Do NOT rewrite, embellish, or change any of the text. Focus on complete and accurate extraction.

    **JSON Structure Requirements:**
    The root JSON object must contain these keys: "personal_info", "summary_paragraphs", "languages", "skills", "work_experience", "education", "hobbies".

    1.  `personal_info`: Extract "name", "job_title", "phone", "email", "city", "zip_code", "linkedin_url".
    2.  `summary_paragraphs`: Extract any summary or "about me" paragraphs as a list of strings.
    3.  `languages`: Extract all languages and their proficiency levels into a list of objects, each with "language" and "level" keys. Example: [{{"language": "German", "level": "Native"}}, {{"language": "English", "level": "Fluent"}}]
    4.  `skills`: Extract all distinct skills into a simple list of strings.
    5.  `work_experience`: Extract EVERY job entry. Each must be an object with "company", "location", "from_date", "to_date", "job_title", "responsibilities" (as a single string), and "achievements" (as a list of strings).
    6.  `education`: Extract EVERY educational entry into a list of objects. Each should have "institution", "degree", "grad_year", and "details".
    7.  `hobbies`: Extract all hobbies into a simple list of strings.

    If information for a key is not found, use an empty string "" or an empty list []. Your entire output must be ONLY the JSON object, without any surrounding text or markdown.

    CONSOLIDATED INPUT TEXT:
    ---
    {consolidated_text}
    ---
    """
    try:
        response = model.generate_content(prompt)
        if not response.parts:
            st.error("🔴 AI Extractor Error: The response was empty. The input might be too complex or trigger a safety filter.")
            return None
        return robust_json_parser(response.text)
    except Exception as e:
        st.error(f"An unexpected error occurred during data extraction: {e}")
        return None

def rewrite_extracted_data(extracted_data, tone_selection):
    """AI Step 2: Takes clean JSON and rewrites the content according to expert rules."""
    # This is our full, detailed, expert rewriting prompt.
    prompt = f"""
    You are a Tier-1 executive career coach and CV writer for the Swiss market. Your task is to take the following CLEAN JSON CV DATA and rewrite ONLY the text values (`summary_paragraphs`, `responsibilities`, `achievements`) to be world-class.
    Do NOT change the structure of the JSON. The output must be the complete, rewritten JSON object and nothing else.

    **Advanced Rewriting Rules based on Tone: {tone_selection}**

    1.  **Professional Summary (`summary_paragraphs`):**
        *   Rewrite into two powerful paragraphs.
        *   **First Paragraph:** Start with the `{tone_selection}` job title. Weave in the top 2-3 areas of expertise and mention years of experience. State the primary value proposition.
        *   **Second Paragraph:** Showcase key achievements with quantifiable results (use metrics like %, CHF, project duration). Connect these achievements to core competencies. Mention key industries (e.g., Pharma, Banking, Tech).
        *   **Tone:** Use strong, confident, and professional language appropriate for the Swiss market. Avoid clichés.

    2.  **Work Experience (`responsibilities` and `achievements`):**
        *   **Responsibilities (`responsibilities`):** Transform the provided text into a concise, powerful paragraph. Focus on the scope and key duties, incorporating relevant keywords for the `{tone_selection}` field.
        *   **Achievements (`achievements`):** This is critical. Rewrite each achievement to follow the STAR method (Situation, Task, Action, Result).
            *   **Action Verbs:** Start every bullet point with a powerful action verb (e.g., "Orchestrated", "Engineered", "Spearheaded", "Negotiated", "Delivered").
            *   **Quantify Everything:** Add metrics wherever possible. If numbers aren't present, you can use phrases like "resulting in significant cost savings" or "enhancing team efficiency by a notable margin," but always prefer concrete numbers.
            *   **Focus on Impact:** Clearly state the benefit to the business (e.g., "...reducing operational costs by 15%", "...which increased customer retention by 10%").

    3.  **General Rules:**
        *   **Buzzwords:** Integrate relevant buzzwords for a `{tone_selection}` role in Switzerland (e.g., 'digital transformation', 'agile methodologies', 'stakeholder management', 'cross-functional leadership', 'data-driven decision-making').
        *   **Clarity & Conciseness:** Ensure the final text is clear, direct, and professional. Remove any fluff or passive language.
        *   **Consistency:** Maintain the selected `{tone_selection}` tone throughout the document.

    Your final output must be ONLY the modified JSON object. Do not add any commentary.

    CLEAN JSON CV DATA TO REWRITE:
    ---
    {json.dumps(extracted_data, indent=2)}
    ---
    """
    try:
        response = model.generate_content(prompt)
        if not response.parts:
            st.error("🔴 AI Rewriter Error: The response was empty. This can happen if the extracted data triggers a safety filter.")
            return None
        return robust_json_parser(response.text)
    except Exception as e:
        st.error(f"An unexpected error occurred during data rewriting: {e}")
        return None

def generate_word_document(context):
    """Renders the final context dictionary into the Word template, escaping special characters."""
    try:
        # This function recursively escapes special XML characters in the context dictionary
        # to prevent errors when rendering the Word document.
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

        # Check for the template file
        if not os.path.exists("CVTemplate_Python.docx"):
            st.error("🔴 Critical Error: The template file 'CVTemplate_Python.docx' was not found. Please ensure it is in the same directory as the script.")
            return None

        doc = DocxTemplate("CVTemplate_Python.docx")
        doc.render(cleaned_context)

        # Save the document to a buffer in memory
        doc_buffer = io.BytesIO()
        doc.save(doc_buffer)
        doc_buffer.seek(0)
        return doc_buffer
    except Exception as e:
        st.error(f"Error generating the Word document: {e}. Please ensure your Word template (.docx) is not corrupt and uses the correct loop syntax (e.g., {{%tr for job in work_experience %}}).")
        st.error("Template context keys being passed: " + str(list(context.keys())))
    return None

# -------------------------------------
# 4. THE MAIN APPLICATION LOGIC
# -------------------------------------
def run_the_app():
    st.sidebar.success("✅ Logged in successfully!")
    st.title("🇨🇭 The Ultimate Swiss CV Enhancer")

    # Initialize session state for storing CV data
    if 'cv_data' not in st.session_state:
        st.session_state.cv_data = None

    # --- STEP 1: UPLOAD AND ANALYZE ---
    st.header("Step 1: Consolidate & Analyse Information")
    st.markdown("Upload your current CV, cover letter, the job description, or any other relevant documents. You can also paste additional text.")

    col1, col2 = st.columns(2)
    with col1:
        uploaded_files = st.file_uploader(
            "Upload relevant documents (.pdf, .docx)",
            type=["pdf", "docx"],
            accept_multiple_files=True
        )
    with col2:
        free_text_input = st.text_area("Or paste any additional text here (e.g., job description, notes):", height=200)

    st.subheader("Select the Desired Tone for your CV")
    tone_selection = st.selectbox(
        "Choose the tone that best fits the target role:",
        ("Executive / Leadership", "Technical / Expert", "Sales / Commercial", "Project Management", "General Professional"),
        key="tone_selector"
    )

    if st.button("🚀 Analyse All Info & Fill Form", type="primary", use_container_width=True):
        all_texts = [free_text_input] if free_text_input else []
        if uploaded_files:
            for file in uploaded_files:
                text = extract_text_from_file(file)
                if text:
                    all_texts.append(text)

        if not all_texts:
            st.warning("Please upload at least one file or provide some text.")
        else:
            consolidated_text = "\n\n--- DOCUMENT SEPARATOR ---\n\n".join(all_texts)

            with st.spinner("🤖 Step 1/2: Extracting all data from documents... This may take a moment."):
                extracted_data = extract_raw_data(consolidated_text)

            if extracted_data:
                st.info("✅ Data extracted. Now polishing content...")
                with st.spinner(f"🤖 Step 2/2: Rewriting and polishing content for a '{tone_selection}' role..."):
                    rewritten_data = rewrite_extracted_data(extracted_data, tone_selection)
                    if rewritten_data:
                        st.session_state.cv_data = rewritten_data
                        st.success("✨ Success! The form below is now filled with enhanced content. Please review before generating.")
                        st.balloons()
                    else:
                        st.error("Data rewriting failed. Please review the AI's output if provided above and try again.")
            else:
                st.error("Data extraction failed. Please check your documents or try rephrasing your notes.")

    # --- STEP 2: REVIEW, EDIT, AND GENERATE ---
    if st.session_state.cv_data:
        st.header("Step 2: Review, Edit, and Generate Final Document")
        st.info("You can now edit any of the AI-generated text below. Your changes will be saved in the final document.")

        data = st.session_state.cv_data
        
        # Use a form to collect all the user edits at once
        with st.form(key='cv_editor_form'):
            # --- Personal Information ---
            with st.expander("👤 Personal Information", expanded=True):
                p_info = data.get('personal_info', {})
                col1, col2 = st.columns(2)
                p_info['name'] = col1.text_input("Full Name", p_info.get('name'), key="name")
                p_info['job_title'] = col2.text_input("Target Job Title", p_info.get('job_title'), key="job_title")
                p_info['email'] = col1.text_input("Email", p_info.get('email'), key="email")
                p_info['phone'] = col2.text_input("Phone", p_info.get('phone'), key="phone")
                p_info['city'] = col1.text_input("City", p_info.get('city'), key="city")
                p_info['zip_code'] = col2.text_input("ZIP Code", p_info.get('zip_code'), key="zip_code")
                p_info['linkedin_url'] = st.text_input("LinkedIn Profile URL", p_info.get('linkedin_url'), key="linkedin_url")

            # --- Professional Summary ---
            with st.expander("📄 Professional Summary", expanded=True):
                summaries = data.get('summary_paragraphs', ['', ''])
                summary_1 = st.text_area("Summary Paragraph 1", summaries[0] if len(summaries) > 0 else "", height=150, key="summary_1")
                summary_2 = st.text_area("Summary Paragraph 2", summaries[1] if len(summaries) > 1 else "", height=150, key="summary_2")

            # --- Work Experience ---
            with st.expander("💼 Work Experience", expanded=True):
                if 'work_experience' in data and data['work_experience']:
                    for i, job in enumerate(data['work_experience']):
                        st.markdown(f"--- \n**Job {i+1}**")
                        col1, col2 = st.columns(2)
                        job['job_title'] = col1.text_input("Job Title", job.get('job_title'), key=f"we_title_{i}")
                        job['company'] = col2.text_input("Company", job.get('company'), key=f"we_company_{i}")
                        job['location'] = col1.text_input("Location", job.get('location'), key=f"we_location_{i}")
                        job['from_date'] = col2.text_input("From Date", job.get('from_date'), key=f"we_from_{i}")
                        job['to_date'] = col1.text_input("To Date", job.get('to_date'), key=f"we_to_{i}")
                        job['responsibilities'] = st.text_area("Responsibilities", job.get('responsibilities'), key=f"we_resp_{i}", height=100)
                        
                        st.markdown("**Achievements**")
                        # Use a text area for achievements, one per line for easier editing
                        ach_text = "\n".join(job.get('achievements', []))
                        edited_ach_text = st.text_area("Achievements (one per line)", ach_text, key=f"we_ach_{i}", height=120)
                        job['achievements'] = [line.strip() for line in edited_ach_text.split('\n') if line.strip()]


            # --- Skills, Languages, Hobbies ---
            col1, col2, col3 = st.columns(3)
            with col1:
                with st.expander("🛠️ Skills"):
                    skills_text = ", ".join(data.get('skills', []))
                    edited_skills = st.text_area("Skills (comma separated)", skills_text, key="skills")
            with col2:
                with st.expander("🌐 Languages"):
                    lang_text = "\n".join([f"{l['language']}: {l['level']}" for l in data.get('languages', [])])
                    edited_langs = st.text_area("Languages (Name: Level)", lang_text, key="languages")
            with col3:
                with st.expander("🎨 Hobbies"):
                    hobbies_text = ", ".join(data.get('hobbies', []))
                    edited_hobbies = st.text_area("Hobbies (comma separated)", hobbies_text, key="hobbies")

            # --- Education ---
            with st.expander("🎓 Education & Qualifications"):
                if 'education' in data and data['education']:
                    for i, edu in enumerate(data['education']):
                        st.markdown(f"--- \n**Qualification {i+1}**")
                        col1, col2 = st.columns(2)
                        edu['degree'] = col1.text_input("Degree/Qualification", edu.get('degree'), key=f"edu_degree_{i}")
                        edu['institution'] = col2.text_input("Institution", edu.get('institution'), key=f"edu_inst_{i}")
                        edu['grad_year'] = col1.text_input("Year", edu.get('grad_year'), key=f"edu_year_{i}")
                        edu['details'] = col2.text_input("Details (Optional)", edu.get('details'), key=f"edu_details_{i}")

            # --- Form Submission ---
            st.markdown("---")
            submit_button = st.form_submit_button(
                label='📄 Generate Final Word Document',
                use_container_width=True
            )

        if submit_button:
            # --- CONSTRUCT THE FINAL CONTEXT FROM THE FORM DATA ---
            final_context = {}
            
            # This logic is critical: it rebuilds the context from the form's state (st.session_state)
            # which now holds all the user's edits.
            
            # Personal Info
            final_context['personal_info'] = {
                'name': st.session_state.name,
                'job_title': st.session_state.job_title,
                'email': st.session_state.email,
                'phone': st.session_state.phone,
                'city': st.session_state.city,
                'zip_code': st.session_state.zip_code,
                'linkedin_url': st.session_state.linkedin_url
            }
            # Summary
            final_context['summary_paragraph_1'] = st.session_state.summary_1
            final_context['summary_paragraph_2'] = st.session_state.summary_2
            
            # Work Experience
            final_context['work_experience'] = []
            for i, _ in enumerate(st.session_state.cv_data['work_experience']):
                job = {
                    'job_title': st.session_state[f'we_title_{i}'],
                    'company': st.session_state[f'we_company_{i}'],
                    'location': st.session_state[f'we_location_{i}'],
                    'from_date': st.session_state[f'we_from_{i}'],
                    'to_date': st.session_state[f'we_to_{i}'],
                    'responsibilities': st.session_state[f'we_resp_{i}'],
                    'achievements': [line.strip() for line in st.session_state[f'we_ach_{i}'].split('\n') if line.strip()]
                }
                final_context['work_experience'].append(job)

            # Education
            final_context['education'] = []
            if 'education' in st.session_state.cv_data:
                for i, _ in enumerate(st.session_state.cv_data['education']):
                    edu = {
                        'degree': st.session_state[f'edu_degree_{i}'],
                        'institution': st.session_state[f'edu_inst_{i}'],
                        'grad_year': st.session_state[f'edu_year_{i}'],
                        'details': st.session_state[f'edu_details_{i}']
                    }
                    final_context['education'].append(edu)

            # Skills, Languages, Hobbies
            final_context['skills'] = [s.strip() for s in st.session_state.skills.split(',') if s.strip()]
            final_context['hobbies'] = [h.strip() for h in st.session_state.hobbies.split(',') if h.strip()]
            final_context['languages'] = []
            for line in st.session_state.languages.split('\n'):
                if ':' in line:
                    lang, _, level = line.partition(':')
                    final_context['languages'].append({'language': lang.strip(), 'level': level.strip()})
            
            with st.spinner("Creating your polished Word document..."):
                doc_buffer = generate_word_document(final_context)
                if doc_buffer:
                    st.success("✅ Document Generated!")
                    st.download_button(
                        label="📥 Download Your Enhanced CV",
                        data=doc_buffer,
                        file_name=f"Enhanced_CV_{final_context['personal_info'].get('name', 'CV')}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )


# -------------------------------------
# 5. PASSWORD CHECK (Corrected Version)
# -------------------------------------
def check_password():
    """Returns `True` if the user entered the correct password."""
    try:
        # Check if the password has already been verified in the current session.
        if st.session_state.get("password_correct", False):
            return True

        # If not verified, display the password input form.
        st.title("🔐 Secure Access")
        password = st.text_input("Please enter the password to access the tool:", type="password", key="password_input")

        # Use st.secrets for password storage comparison.
        correct_password = st.secrets.get("APP_PASSWORD")
        if not correct_password:
             st.error("🔴 Critical Error: Application password is not configured in st.secrets. Please contact the administrator.")
             return False

        if password == correct_password:
            st.session_state.password_correct = True
            # This is the corrected line:
            st.rerun() # Use the modern `st.rerun()` to reload the app state.
        elif password: # If the user has entered any password and it's wrong
            st.error("Password incorrect. Please try again.")
        else: # If the field is empty
            st.info("A password is required to use this application.")
        
        return False

    except Exception as e:
        st.error(f"🔴 An unexpected error occurred in the password check function: {e}")
        return False

# --- Main script execution ---
if check_password():
    run_the_app()
