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
    st.error("🔴 Critical Error: Cannot connect to the AI service.")
    st.stop()

# -------------------------------------
# 3. HELPER FUNCTIONS
# -------------------------------------

def get_prompts(language, extracted_data, tone_selection, consolidated_text):
    """
    Returns the appropriate extraction and rewriting prompts based on the selected language.
    """
    if language == "German":
        # The robust, analytical extraction prompt for German
        extraction_prompt = f"""
        Sie sind eine hochintelligente Datenextraktions-Engine, spezialisiert auf die Analyse von deutschsprachigen Lebensläufen mit variierenden Layouts. Ihre Aufgabe ist es, den Text zu analysieren, seine Struktur zu verstehen und dann die Informationen präzise zu extrahieren.

        ### ANALYTISCHES FRAMEWORK (Zuerst denken, dann extrahieren)
        1.  **Layout-Analyse:** Identifizieren Sie zuerst die Struktur des Dokuments. Ist es einspaltig? Zweispaltig? Behandeln Sie jede Spalte als unabhängigen Container für zusammengehörige Informationen.
        2.  **Informations-Identifikation (Heuristiken):** Suchen Sie nach dem prominentesten Text am Anfang von Seite 1 für den Namen. Suchen Sie nach Mustern wie '@' für E-Mail und '+' für Telefon.
        3.  **Daten-Assoziation (KRITISCHE REGELN):** Daten in einer Spalte dürfen NUR mit anderen Daten in DERSELBEN SPALTE in Verbindung gebracht werden. Innerhalb einer Spalte gehört eine Datumsangabe zu dem Eintrag unmittelbar darüber, daneben oder darunter.

        **ANFORDERUNGEN AN DIE JSON-STRUKTUR (VOLLSTÄNDIGE LISTE):**
        1.  `personal_info`: Extrahieren Sie "name", "job_title", "phone", "email", "city", "zip", "country", "linkedin_url".
        2.  `summary_paragraphs`: Extrahieren Sie Abschnitte wie "Profil".
        3.  `languages`: Extrahieren Sie alle Sprachen und Niveaus.
        4.  `skills`: Extrahieren Sie alle Fähigkeiten.
        5.  `work_experience`: Extrahieren Sie JEDEN Jobeintrag. Jedes Objekt MUSS "company", "from_date", "to_date", "job_title", "responsibility", und "achievements" enthalten.
        6.  `education`: Extrahieren Sie JEDEN Bildungseintrag.
        7.  `hobbies`: Extrahieren Sie alle Hobbys.

        Wenn Informationen fehlen, verwenden Sie einen leeren String "" oder eine leere Liste []. Ihre gesamte Ausgabe muss NUR das JSON-Objekt sein.
        ZUSAMMENGEFASSTER EINGABETEXT: --- {consolidated_text} ---
        """
        
        tone_map_de = {
            "Executive / Leadership": "Führungskraft / Management",
            "Technical / Expert": "Technischer Experte / Spezialist",
            "Sales / Commercial": "Vertrieb / Kommerziell",
            "Project Management": "Projektmanagement",
            "General Professional": "Allgemein / Fachlich"
        }
        german_tone = tone_map_de.get(tone_selection, "Allgemein / Fachlich")

        rewriting_prompt = f"""
        Sie agieren als hochqualifizierter Karriereberater und Texter für den Schweizer Markt. Ihre Aufgabe ist es, die rohen JSON-Daten in eine ausgefeilte, professionelle und faktenbasierte Erzählung zu verwandeln, die strategisch auf die Zielposition ausgerichtet ist und strenge Limiten einhält.

        ROHDATEN (VON SCHRITT 1): --- {json.dumps(extracted_data, indent=2)} ---
        VOLLSTÄNDIGER KONTEXT (enthält Lebenslauf & potentielle Stellenbeschreibung): --- {consolidated_text} ---

        **FINALE JSON-STRUKTUR (STRENG BEFOLGEN):**
        Das JSON-Stammobjekt muss die Schlüssel "personal_info", "summary_paragraphs", "languages", "skills", "work_experience", "education", "hobbies" enthalten.
        - `personal_info`: Objekt mit "NAME", "JOB_TITLE", "phone", "email", "city", "zip", "country", "Linkedin".
        - `summary_paragraphs`: Liste mit zwei Strings.
        - `languages`, `skills`, `hobbies`: Listen mit max. 6 Einträgen.
        - `work_experience`, `education`: Listen mit max. 10 Einträgen.

        ---
        **Regeln für die Überarbeitung und Inhaltserstellung:**

        **1. Kernanalyse & `JOB_TITLE`:**
        - Analysieren Sie den VOLLSTÄNDIGEN KONTEXT. Wenn eine Stellenbeschreibung vorhanden ist, leiten Sie den **`JOB_TITLE` (Ziel-Jobtitel)** daraus ab. Andernfalls erstellen Sie eine professionelle, zukunftsorientierte Überschrift basierend auf der letzten Position.
        - **`personal_info.NAME`:** Schreiben Sie den Namen in Grossbuchstaben.

        **2. Ton und Sprache (KRITISCH):**
        - **Sprache:** Schweizer Hochdeutsch (kein 'ß', immer 'ss').
        - **Dynamischer Ton basierend auf der Wahl '{german_tone}'**: Passen Sie Vokabular, Formulierungen und Schwerpunkte exakt an:
            - **'Führungskraft / Management':** Fokus auf Strategie, Vision, GuV-Verantwortung, Teamführung. Verben wie "leitete", "steuerte", "orchestrierte". Betonen Sie Finanzkennzahlen, Teamgrösse, Stakeholder-Management.
            - **'Technischer Experte / Spezialist':** Fokus auf Fachexpertise, technische Kompetenz, Problemlösung. Verben wie "entwickelte", "konzipierte", "analysierte". Betonen Sie Technologien, Methoden, Zertifizierungen.
            - **'Vertrieb / Kommerziell':** Fokus auf Umsatzgenerierung, Marktwachstum, Kundenakquise. Verben wie "akquirierte", "erzielte", "übertraf". Betonen Sie quantifizierbare Vertriebserfolge (CHF, %), Quotenerreichung.
            - **'Projektmanagement':** Fokus auf termingerechte/budgetkonforme Lieferung, Prozesseffizienz. Verben wie "lieferte", "managte", "koordinierte". Betonen Sie Projektumfang, Methoden.
            - **'Allgemein / Fachlich':** Fokus auf Kompetenz, Zuverlässigkeit, Zusammenarbeit. Verben wie "unterstützte", "verbesserte", "organisierte".

        **3. Kurzprofil (`summary_paragraphs`):**
        - **Absatz 1 (Genau 2 Sätze, max. 310 Zeichen, quantifizieren):**
            - **Satz 1:** Definiert die professionelle Identität (z.B. "Vertriebsleiter mit 15 Jahren Erfahrung...").
            - **Satz 2:** Nennt den wichtigsten quantifizierbaren Erfolg der jüngsten Karriere (z.B. "Zuletzt steigerte ich das regionale Wachstum um 18 %...").
        - **Absatz 2 (Ich-Perspektive, max. 160 Zeichen):**
            - Synthetisiert die Kernmotivation und Werte des Kandidaten.

        **4. Berufserfahrung (`work_experience`) - MAX 10:**
        - **Schlüssel:** Benennen Sie `job_title` zu `title`, `from_date` zu `from`, `to_date` zu `to` um.
        - **Verantwortung:** 1-2 prägnante, sachliche Sätze zum Aufgabenbereich.
        - **Erfolge (KRITISCH - Erfolgsgeschichten formulieren):**
            - Wandeln Sie die Stichpunkte in 1 bis 3 aussagekräftige Erfolgsgeschichten pro Job um.
            - Jede Geschichte muss eine detaillierte, einzelne Antwort auf die Fragen "Was habe ich erreicht?", "Wie habe ich es getan?" und "Warum war es wichtig?" geben.
            - **Perfektes Beispiel:** "Durch die Untersuchung und Qualitätsprüfung von über 2.000 ICSR-Fällen gemäss GCP-, FDA- und ICH-Richtlinien erreichte ich eine Reduzierung der Datendiskrepanzen um 15 % und stellte eine 100-prozentige Inspektionsbereitschaft sicher."
            - **Obligatorische Vorgaben:** Formulieren Sie aus der Ich-Perspektive. Jeder Satz sollte ca. 25-45 Wörter lang sein.

        **5. Negative Einschränkungen (UNBEDINGT VERMEIDEN):**
        - Kein Passiv. Vermeiden Sie strikt: `ergebnisorientiert`, `dynamisch`, `leidenschaftlich`, `Teamplayer`, `motiviert`, `proaktiv`, `innovativ`, `strategischer Denker`.
        - Zeigen Sie Qualitäten durch Fakten, benennen Sie sie nicht.

        **Letzte Anweisung:** Ihre gesamte Ausgabe MUSS ein einziges, valides JSON-Objekt sein.
        """
    else:  # Default to English
        # The robust, analytical extraction prompt for English
        extraction_prompt = f"""
        You are a highly intelligent data extraction engine specializing in analyzing CVs with various layouts. Your task is to analyze the document's structure, understand the context, and then precisely extract the information.

        ### ANALYTICAL FRAMEWORK (Think First, Then Extract)
        1.  **Layout & Column Analysis:** First, identify the document's structure. Is it single-column? Two-column? **Treat columns as independent containers of related information.**
        2.  **Information Identification (Heuristics):** Look for the most prominent text at the top of page 1 for the name. Look for patterns like '@' for email and '+' for phone numbers.
        3.  **Data Association (CRITICAL RULES):** Data in one column can **ONLY** be associated with other data in the **SAME COLUMN**. Within a single column, a date is associated with the most plausible entry (like a degree or job title) that is immediately **above, on the same line, or immediately below it.**

        **JSON STRUCTURE REQUIREMENTS (COMPLETE LIST):**
        1.  `personal_info`: Extract "name", "job_title", "phone", "email", "city", "zip", "country", "linkedin_url".
        2.  `summary_paragraphs`: Extract sections like "Profile" or "Summary".
        3.  `languages`: Extract all languages and proficiency levels.
        4.  `skills`: Extract all skills.
        5.  `work_experience`: Extract EVERY job entry. Each object MUST include "company", "from_date", "to_date", "job_title", "responsibility", and "achievements".
        6.  `education`: Extract EVERY educational entry.
        7.  `hobbies`: Extract all hobbies.

        If information is missing, use an empty string "" or an empty list []. Your entire output must be ONLY the JSON object.
        CONSOLIDATED INPUT TEXT: --- {consolidated_text} ---
        """
        # The excellent, full rewrite prompt from your working script
        rewriting_prompt = f"""
        You are a meticulous and precise professional CV editor for the Swiss market. Your task is to refine the provided raw JSON data into a polished, professional, and factual narrative that is strategically aligned with the target job, adhering to strict limits.

        RAW EXTRACTED CV DATA (FROM STEP 1):
        ---
        {json.dumps(extracted_data, indent=2)}
        ---

        FULL CONTEXT (includes CV and potential Job Description for analysis):
        ---
        {consolidated_text}
        ---

        **JSON Structure Requirements for FINAL OUTPUT (Strictly follow this):**
        The root JSON object must contain these keys: "personal_info", "summary_paragraphs", "languages", "skills", "work_experience", "education", "hobbies".
        - `personal_info`: Object with keys "NAME", "JOB_TITLE", "phone", "email", "city", "zip", "country", "Linkedin".
        - `summary_paragraphs`: List of two strings.
        - `languages`: List of objects, each with "language" and "level". **MAXIMUM of 6.**
        - `skills`: List of strings. **MAXIMUM of 6.**
        - `work_experience`: List of objects. **MAXIMUM of 10.**
        - `education`: List of objects. **MAXIMUM of 10.**
        - `hobbies`: List of strings. **MAXIMUM of 6.**

        ---

        **Advanced Rewriting and Content Generation Rules:**

        **1. Core Analysis & `JOB_TITLE` Determination:**
        - Analyze the FULL CONTEXT to identify if a future job description is present.
        - **`JOB_TITLE`:** If a job description exists, derive the `JOB_TITLE` from it. Otherwise, create a professional, grounded future headline based on their most recent role.
        - **`personal_info.NAME`:** Capitalize the person's name.

        **2. Tone and Language (CRITICAL):**
        - **Language:** Use British English.
        - **Dynamic Tone Selection based on user's choice: '{tone_selection}'**. You must adapt your vocabulary, phrasing, and the aspects of the candidate's experience you highlight based on the following detailed rules:
            - **If 'Executive / Leadership':** Core Focus on strategy, vision, P&L responsibility, team leadership. Emphasize financial metrics, team size, C-level stakeholder management.
            - **If 'Technical / Expert':** Core Focus on deep domain knowledge, technical proficiency. Emphasize specific technologies, methodologies, certifications.
            - **If 'Sales / Commercial':** Core Focus on revenue generation, market growth, client acquisition. Emphasize quantifiable sales results (CHF, %), quota attainment.
            - **If 'Project Management':** Core Focus on on-time/on-budget delivery, process efficiency. Emphasize project scope, methodologies.
            - **If 'General Professional':** Core Focus on competence, reliability, effective collaboration. Emphasize key responsibilities, teamwork, process improvements.

        **3. Professional Summary (`summary_paragraphs`):**
        - **Paragraph 1 (Strictly Two Sentences, max 310 chars, quantify whenever possible):**
            - **Sentence 1:** Define the candidate's professional identity (e.g., "Commercial Leader with 15 years of experience in the biotech sector.").
            - **Sentence 2:** State their single most impressive and quantifiable achievement from their recent career (e.g., "Most recently, drove regional growth by 18%...").
        - **Paragraph 2 (First-person "I", max 160 chars):**
            - Synthesize the candidate's core motivators and values. **Strictly adhere to a maximum of 160 characters (including spaces).**

        **4. Work experience (`work_experience`) - Max 10 entries:**
        - Prioritize the most recent and relevant roles.
        - Rename keys: `job_title` to `title`, `from_date` to `from`, `to_date` to `to`.
        - **Responsibility**: Write 1-2 concise, factual sentences describing the role's scope.
        - **Achievements (CRITICAL - Crafting Success Stories):**
            - Transform simple bullet points into 1 to 3 powerful, personal success stories for each job.
            - Each story must be a single, detailed sentence that answers: "What did I accomplish?", "How did I do it?", and "Why did it matter?".
            - **Perfect Example:** "By investigating and quality-checking over 2,000 ICSR cases..., I achieved a 15% reduction in data discrepancies and ensured 100% inspection-readiness."
            - **Mandatory Constraints:** Frame from the first-person perspective. Each sentence should be approx. 25-45 words long. Use only available information.

        **5. Skills Selection & Prioritization (CRITICAL - MAX 6):**
        - Analyze all skills and select the six (6) most relevant to the job description.

        **6. Language & Hobbies (CRITICAL - MAX 6 each):**
        - For `languages`, select a maximum of 6, prioritizing the highest proficiency.
        - For `hobbies`, select a maximum of 6 relevant entries.

        **7. Education (MAX 10):**
        - Select a maximum of 10 education entries. Rename `graduation_date` to `graduation`.

        **8. Negative Constraints (AVOID AT ALL COSTS):**
        - No Passive Voice. Strictly avoid: seasoned, results-driven, dynamic, motivated, proven track record, passionate, innovative, creative thinker, strategic thinker, team player, etc.
        - Demonstrate qualities, do not state them.

        **Final Instruction:** Your entire output MUST be a single, valid JSON object.
        """

    return extraction_prompt, rewriting_prompt


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
        st.error(f"Error reading file: {uploaded_file.name}.")
    return ""

def robust_json_parser(raw_text_from_ai):
    """A more robust JSON parser that handles common AI errors."""
    try:
        clean_text = re.sub(r'^```json\s*|```\s*$', '', raw_text_from_ai.strip())
        start = clean_text.find('{')
        end = clean_text.rfind('}') + 1
        if start == -1 or end == 0: raise ValueError("JSON object not found.")
        clean_json_text = clean_text[start:end]
        clean_json_text = re.sub(r',\s*([}\]])', r'\1', clean_json_text)
        return json.loads(clean_json_text)
    except (ValueError, json.JSONDecodeError) as e:
        st.error(f"🔴 Error: Could not parse the AI's response. Details: {e}")
        st.text_area("Raw AI output:", raw_text_from_ai, height=200)
        return None

def extract_raw_data(prompt):
    """AI STEP 1: Extracts raw data."""
    try:
        response = model.generate_content(prompt)
        if not response.parts: return None
        return robust_json_parser(response.text)
    except Exception as e:
        st.error(f"An unexpected error occurred during data extraction: {e}")
        return None

def rewrite_extracted_data(prompt):
    """AI STEP 2: Rewrites data using your final, locked-in expert prompt."""
    try:
        response = model.generate_content(prompt)
        if not response.parts: return None
        return robust_json_parser(response.text)
    except Exception as e:
        st.error(f"An unexpected error occurred during data rewriting: {e}")
        return None

def generate_word_document(context, language):
    """
    Renders the final context into the correct Word template based on language.
    """
    try:
        if language == "German":
            template_name = "CVTemplate_Python_DE.docx"
        else: # Default to English
            template_name = "CVTemplate_Python_EN.docx"
            
        if not os.path.exists(template_name):
            st.error(f"🔴 Critical Error: The template file '{template_name}' was not found.")
            st.info(f"Please make sure you have two templates: 'CVTemplate_Python_EN.docx' and 'CVTemplate_Python_DE.docx' in the same folder as the script.")
            return None
        
        doc = DocxTemplate(template_name)

        def safe_escape_data(data):
            if isinstance(data, dict):
                return {k: safe_escape_data(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [safe_escape_data(item) for item in data]
            elif isinstance(data, str):
                return escape(data)
            else:
                return data

        safe_context = safe_escape_data(context)
        doc.render(safe_context)
        
        doc_buffer = io.BytesIO()
        doc.save(doc_buffer)
        doc_buffer.seek(0)
        return doc_buffer
    except Exception as e:
        st.error(f"Error generating the Word document: {e}. Check your Word template syntax.")
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

    col_tone, col_lang = st.columns(2)
    with col_tone:
        tone_selection = st.selectbox("Select the Desired Tone:", ("Executive / Leadership", "Technical / Expert", "Sales / Commercial", "Project Management", "General Professional"))
    with col_lang:
        language_selection = st.selectbox("Select the Output Language:", ("English", "German"))

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
            
            extraction_prompt, _ = get_prompts(language_selection, {}, "", consolidated_text)
            
            with st.spinner("🤖 Step 1/2: Analyzing document and extracting raw data..."):
                extracted_data = extract_raw_data(extraction_prompt)
            
            if extracted_data:
                st.info("✅ Raw data extracted. Now applying expert rewriting rules...")
                
                _, rewriting_prompt = get_prompts(language_selection, extracted_data, tone_selection, consolidated_text)
                
                spinner_text = (f"🤖 Schritt 2/2: Inhalte werden auf Deutsch für eine '{tone_selection}'-Rolle optimiert..." if language_selection == "German" 
                              else f"🤖 Step 2/2: Rewriting content and selecting top items for a '{tone_selection}' role...")
                
                with st.spinner(spinner_text):
                    rewritten_data = rewrite_extracted_data(rewriting_prompt)
                    if rewritten_data:
                        st.session_state.cv_data = rewritten_data
                        success_text = "✨ Erfolg! Das Formular ist ausgefüllt." if language_selection == "German" else "✨ Success! The form is filled."
                        st.success(f"{success_text} Review and edit the content below.")
                        st.balloons()
                    else: st.error("AI Rewriting Failed.")
            else: st.error("AI Extraction Failed.")

    if st.session_state.cv_data:
        st.header("Step 2: Review, Edit, and Generate")
        data = st.session_state.cv_data
        with st.form(key='cv_editor_form'):
            with st.expander("👤 Personal Information", expanded=True):
                p_info = data.get('personal_info', {})
                st.text_input("Full Name", p_info.get('NAME', ''), key="p_NAME")
                st.text_input("Target Job Title", p_info.get('JOB_TITLE', ''), key="p_JOB_TITLE")
                st.text_input("Email", p_info.get('email', ''), key="p_email")
                st.text_input("Phone", p_info.get('phone', ''), key="p_phone")
                st.text_input("City", p_info.get('city', ''), key="p_city")
                st.text_input("ZIP", p_info.get('zip', ''), key="p_zip")
                st.text_input("Country", p_info.get('country', ''), key="p_country")
                st.text_input("LinkedIn Profile URL", p_info.get('Linkedin', ''), key="p_Linkedin")

            with st.expander("📄 Professional Summary", expanded=True):
                summaries = data.get('summary_paragraphs', ['', ''])
                st.text_area("Summary Paragraph 1", summaries[0] if len(summaries) > 0 else "", height=100, key="summary_1", max_chars=310)
                st.text_area("Summary Paragraph 2 (first-person 'I')", summaries[1] if len(summaries) > 1 else "", height=80, key="summary_2", max_chars=160)

            with st.expander("💼 Work Experience (Max 10)", expanded=True):
                for i, job in enumerate(data.get('work_experience', [])[:10]):
                    st.markdown(f"--- \n**Job {i+1}**")
                    st.text_input(f"Job Title", job.get('title', ''), key=f"we_title_{i}")
                    st.text_input(f"Company", job.get('company', ''), key=f"we_company_{i}")
                    col1, col2 = st.columns(2)
                    col1.text_input(f"From Date", job.get('from', ''), key=f"we_from_{i}")
                    to_date_display = job.get('to', '')
                    if i == 0 and not to_date_display:
                        to_date_display = 'Present'
                    col2.text_input(f"To Date", to_date_display, key=f"we_to_{i}")
                    st.text_area(f"Responsibility", job.get('responsibility', ''), key=f"we_resp_{i}", height=100)
                    st.text_area(f"Achievements (one per line)", "\n".join(job.get('achievements', [])), key=f"we_ach_{i}", height=120)

            with st.expander("🎓 Education & Qualifications (Max 10)", expanded=True):
                for i, edu in enumerate(data.get('education', [])[:10]):
                    st.markdown(f"--- \n**Qualification {i+1}**")
                    st.text_input(f"Degree/Qualification", edu.get('degree', ''), key=f"edu_degree_{i}")
                    st.text_input(f"Graduation Date", edu.get('graduation', ''), key=f"edu_graduation_{i}")
                    st.text_input(f"University/Institution", edu.get('university', ''), key=f"edu_university_{i}")
                    st.text_input(f"University Location", edu.get('university_location', ''), key=f"edu_location_{i}")
                    st.text_input(f"University Country", edu.get('university_country', ''), key=f"edu_country_{i}")

            with st.expander("🛠️ Skills, Languages & Hobbies"):
                col1, col2 = st.columns(2)
                with col1:
                    st.text_area("Skills (Max 6 - one per line)", "\n".join(data.get('skills', [])[:6]), key="skills", height=200)
                with col2:
                    st.text_area("Languages (Max 6 - Name: Level)", "\n".join([f"{l.get('language', '')}: {l.get('level', '')}" for l in data.get('languages', [])[:6]]), key="languages", height=200)
                st.text_area("Hobbies & Extracurricular (Max 6 - one per line)", "\n".join(data.get('hobbies', [])[:6]), key="hobbies", height=150)

            submit_button = st.form_submit_button(label='📄 Generate Final Word Document', use_container_width=True)

        if submit_button:
            final_context = {}
            final_context['NAME'] = st.session_state.get('p_NAME', '')
            final_context['JOB_TITLE'] = st.session_state.get('p_JOB_TITLE', '')
            final_context['phone'] = st.session_state.get('p_phone', '')
            final_context['email'] = st.session_state.get('p_email', '')
            final_context['city'] = st.session_state.get('p_city', '')
            final_context['zip'] = st.session_state.get('p_zip', '')
            final_context['country'] = st.session_state.get('p_country', '')
            final_context['Linkedin'] = st.session_state.get('p_Linkedin', '')
            final_context['summary_paragraph_1'] = st.session_state.get('summary_1', '')
            final_context['summary_paragraph_2'] = st.session_state.get('summary_2', '')
            
            work_experience_list = []
            work_experience_data = data.get('work_experience', [])[:10]
            for i, _ in enumerate(work_experience_data):
                to_date_value = st.session_state.get(f'we_to_{i}', '')
                job_data = {
                    'title': st.session_state.get(f'we_title_{i}', ''),
                    'company': st.session_state.get(f'we_company_{i}', ''),
                    'from': st.session_state.get(f'we_from_{i}', ''),
                    'to': to_date_value,
                    'responsibility': st.session_state.get(f'we_resp_{i}', ''),
                    'achievements': [line.strip() for line in st.session_state.get(f'we_ach_{i}', '').split('\n') if line.strip()]
                }
                if i == 0 and (not job_data['to'] or job_data['to'].lower() == 'present'):
                    job_data['to'] = 'Present'
                work_experience_list.append(job_data)
            final_context['work_experience'] = work_experience_list
            
            education_data = data.get('education', [])[:10]
            final_context['education'] = [
                {
                    'degree': st.session_state.get(f'edu_degree_{i}', ''),
                    'graduation': st.session_state.get(f'edu_graduation_{i}', ''),
                    'university': st.session_state.get(f'edu_university_{i}', ''),
                    'university_location': st.session_state.get(f'edu_location_{i}', ''),
                    'university_country': st.session_state.get(f'edu_country_{i}', '')
                } for i, _ in enumerate(education_data)
            ]
            
            final_context['skills'] = [s.strip() for s in st.session_state.get('skills', '').split('\n') if s.strip()][:6]
            final_context['languages'] = [{'language': line.partition(':')[0].strip(), 'level': line.partition(':')[2].strip()} for line in st.session_state.get('languages', '').split('\n') if ':' in line][:6]
            final_context['hobbies'] = [h.strip() for h in st.session_state.get('hobbies', '').split('\n') if h.strip()][:6]

            with st.spinner("Creating your polished Word document..."):
                doc_buffer = generate_word_document(final_context, language_selection)
                if doc_buffer:
                    st.success("✅ Document Generated!")
                    
                    file_name = (f"Optimierter_Lebenslauf_{final_context.get('NAME', 'CV')}.docx" if language_selection == "German" 
                                 else f"Enhanced_CV_{final_context.get('NAME', 'CV')}.docx")
                    label = "📥 Ihren optimierten Lebenslauf herunterladen" if language_selection == "German" else "📥 Download Your Enhanced CV"

                    st.download_button(
                        label=label, 
                        data=doc_buffer, 
                        file_name=file_name, 
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                        use_container_width=True
                    )

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
if __name__ == "__main__":
    if check_password():
        run_the_app()
