import re
import time
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import anthropic

anthropic_api_key = st.secrets["anthropic"]["anthropic_api_key"]
client = anthropic.Client(api_key=anthropic_api_key)

possible_columns = [
    "Text01", "Text01-1", "Text01-2", "Text01-3", "Text01-4", "01BG-Theme-Text",
    "Text02", "Text02-1", "Text02-2", "Text02-3", "Text02-4", "02BG-Theme-Text",
    "Text03", "Text03-1", "Text03-2", "Text03-3", "Text03-4", "03BG-Theme-Text",
    "Text04", "Text04-1", "Text04-2", "Text04-3", "Text04-4", "04BG-Theme-Text",
    "Text05", "Text05-1", "Text05-2", "Text05-3", "Text05-4", "05BG-Theme-Text",
    "CTA-Text", "CTA-Text-1", "CTA-Text-2", "Tagline-Text"
]

def clean_job_id(job_id):
    if not job_id:
        return None
    return job_id.strip().lower()

@st.cache_data
def load_google_sheet(sheet_id):
    credentials_info = st.secrets["google_credentials"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        data = pd.DataFrame(sheet.get_all_records())
        return data
    except gspread.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found.")
        return pd.DataFrame()

@st.cache_data
def load_template_csv():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    try:
        examples = pd.read_csv(url)
        return examples
    except Exception as e:
        st.error(f"Error loading examples CSV: {e}")
        return pd.DataFrame()

def clean_text(text):
    text = re.sub(r'\*\*', '', text)
    emoji_pattern = re.compile(
        "[" 
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF"
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text)

def extract_template_structure(selected_template, examples_data):
    if "template_SH_" in selected_template:
        try:
            template_number = int(selected_template.split('_')[-1])
            template_number_str = f"{template_number:02d}"
        except ValueError:
            template_number_str = "01"
    else:
        template_number_str = "01"

    example_row = examples_data[examples_data['Template'] == f'template_SH_{template_number_str}']
    
    if example_row.empty:
        return None

    template_structure = []
    for col in possible_columns:
        if col in example_row.columns:
            text_element = example_row[col].values[0]
            if pd.notna(text_element):
                template_structure.append((col, text_element))

    return template_structure

def build_template_prompt(sheet_row, template_structure):
    job_id = sheet_row['Job ID']
    topic_description = sheet_row['Topic-Description']

    if not (job_id and topic_description and template_structure):
        return None, None

    prompt = f"Generate content for Job ID {job_id} using the description from the Google Sheet. Follow the section structure exactly as given, ensuring that the content of the umbrella sections is divided verbatim into subsections.\n\n"
    
    prompt += f"Description from Google Sheet:\n{topic_description}\n\n"
    prompt += "For each section, generate content in strict order. Subsections must split the umbrella section verbatim into distinct, meaningful parts. Do not reorder sections or introduce new content:\n\n"

    umbrella_sections = {}
    for section_name, content in template_structure:
        max_chars = len(content)
        if '-' not in section_name:
            umbrella_sections[section_name] = section_name
            prompt += f"Section {section_name}: Generate content based only on the description from the Google Sheet. Stay within {max_chars} characters.\n"
        else:
            umbrella_key = section_name.split('-')[0]
            if umbrella_key in umbrella_sections:
                prompt += f"Section {section_name}: Extract a distinct, verbatim part of the umbrella section '{umbrella_sections[umbrella_key]}'. Ensure that subsections are ordered logically and no new content is introduced.\n"

    if 'CTA-Text' in [section for section, _ in template_structure]:
        prompt += "Ensure a clear call-to-action (CTA-Text) is provided at the end of the content."

    prompt += "\nStrictly generate content for every section, ensuring subsections extract distinct, verbatim parts from the umbrella content in proper order."

    return prompt, job_id

def parse_generated_content(content, job_id):
    sections = {}
    current_section = None
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('Section'):
            current_section = line.split(':')[0].strip()
            sections[current_section] = ''
        elif current_section:
            sections[current_section] += line + ' '
    for key in sections:
        sections[key] = sections[key].strip()
    return sections

def generate_and_split_content(prompt, job_id, retries=3, delay=5):
    for i in range(retries):
        try:
            response = client.completion(
                prompt=anthropic.HUMAN_PROMPT + prompt + anthropic.AI_PROMPT,
                stop_sequences=[anthropic.HUMAN_PROMPT],
                max_tokens_to_sample=1000,
                model="claude-v1",  # Use a valid model name
                temperature=0.7,
            )
            content = response['completion'].strip()
            content_clean = clean_text(content)
            structured_content = parse_generated_content(content_clean, job_id)
            return structured_content
        except Exception as e:
            st.warning(f"Error generating content for Job ID {job_id}: {e}. Retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
            time.sleep(delay)
    return None

def map_content_to_google_sheet(sheet, row_index, structured_content):
    mapping = {
        "Section Text01": "H", "Section Text01-1": "I", "Section Text01-2": "J", "Section Text01-3": "K", "Section Text01-4": "L", "Section 01BG-Theme-Text": "M",
        "Section Text02": "N", "Section Text02-1": "O", "Section Text02-2": "P", "Section Text02-3": "Q", "Section Text02-4": "R", "Section 02BG-Theme-Text": "S",
        "Section Text03": "T", "Section Text03-1": "U", "Section Text03-2": "V", "Section Text03-3": "W", "Section Text03-4": "X", "Section 03BG-Theme-Text": "Y",
        "Section Text04": "Z", "Section Text04-1": "AA", "Section Text04-2": "AB", "Section Text04-3": "AC", "Section Text04-4": "AD", "Section 04BG-Theme-Text": "AE",
        "Section Text05": "AF", "Section Text05-1": "AG", "Section Text05-2": "AH", "Section Text05-3": "AI", "Section Text05-4": "AJ", "Section 05BG-Theme-Text": "AK",
        "Section CTA-Text": "AL", "Section CTA-Text-1": "AM", "Section CTA-Text-2": "AN", "Section Tagline-Text": "AO"
    }

    for section, content in structured_content.items():
        if section in mapping:
            col_letter = mapping[section]
            sheet.update_acell(f'{col_letter}{row_index}', content)
            time.sleep(1)

def update_google_sheet_with_generated_content(sheet_id, job_id, generated_content, retries=3):
    credentials_info = st.secrets["google_credentials"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    
    job_id_normalized = clean_job_id(job_id)

    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        rows = sheet.get_all_values()

        for i, row in enumerate(rows):
            job_id_in_sheet = row[1].strip().lower() if row[1].strip() else None
            if not job_id_in_sheet:
                continue
            
            if job_id_in_sheet == job_id_normalized:
                row_index = i + 1
                if generated_content:
                    map_content_to_google_sheet(sheet, row_index, generated_content)
                st.success(f"Content for Job ID {job_id} successfully updated in the Google Sheet.")
                return True

        st.error(f"No matching Job ID found for '{job_id}' in the target sheet.")
        return False

    except gspread.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found.")
        return False
    except gspread.exceptions.APIError as e:
        if retries > 0 and e.response.status_code == 500:
            st.warning(f"Internal error encountered. Retrying... ({retries} retries left)")
            time.sleep(5)
            return update_google_sheet_with_generated_content(sheet_id, job_id, generated_content, retries-1)
        else:
            st.error(f"An error occurred while updating the Google Sheet: {e.response.json()}")
            return False

def main():
    st.title("AI Script and Content Generator")
    st.markdown("---")

    sheet_id = '1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8'
    request_sheet_id = '1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8'

    sheet_data = load_google_sheet(request_sheet_id)
    examples_data = load_template_csv()

    if sheet_data.empty or examples_data.empty:
        st.error("No data available from the request Google Sheet or the examples CSV.")
        return

    st.dataframe(sheet_data)

    if st.button("Generate Content"):
        for idx, row in sheet_data.iterrows():
            if not row['Job ID']:
                st.warning(f"Row {idx + 1} is missing Job ID. Skipping this row.")
                continue

            job_id = row['Job ID']
            selected_template = row['Selected-Template']
            template_structure = extract_template_structure(selected_template, examples_data)

            if template_structure is None:
                st.error(f"No template found for Job ID {job_id}. Skipping this row.")
                continue

            prompt, job_id = build_template_prompt(row, template_structure)

            if not prompt:
                st.warning(f"Could not build prompt for Job ID {job_id}. Skipping this row.")
                continue

            generated_content = generate_and_split_content(prompt, job_id)

            if generated_content:
                update_google_sheet_with_generated_content(sheet_id, job_id, generated_content)

if __name__ == "__main__":
    main()
