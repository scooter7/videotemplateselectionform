import re
import time
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import anthropic

# Initialize the Anthropic client
anthropic_api_key = st.secrets["anthropic"]["anthropic_api_key"]
client = anthropic.Client(api_key=anthropic_api_key)

# Function to clean job IDs
def clean_job_id(job_id):
    """Clean the job ID by stripping spaces and converting to lowercase."""
    if not job_id:
        return None
    return job_id.strip().lower()

possible_columns = [
    "Text01", "Text01-1", "Text01-2", "Text01-3", "Text01-4", "01BG-Theme-Text",
    "Text02", "Text02-1", "Text02-2", "Text02-3", "Text02-4", "02BG-Theme-Text",
    "Text03", "Text03-1", "Text03-2", "Text03-3", "Text03-4", "03BG-Theme-Text",
    "Text04", "Text04-1", "Text04-2", "Text04-3", "Text04-4", "04BG-Theme-Text",
    "Text05", "Text05-1", "Text05-2", "Text05-3", "Text05-4", "05BG-Theme-Text",
    "CTA-Text", "CTA-Text-1", "CTA-Text-2", "Tagline-Text"
]

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

# Load Google Sheets data based on sheet ID
def load_google_sheet(sheet_id):
    """Load Google Sheets data based on the provided sheet ID."""
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
def load_examples():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    try:
        examples = pd.read_csv(url)
        return examples
    except Exception as e:
        st.error(f"Error loading examples CSV: {e}")
        return pd.DataFrame()

# Extract the template structure and max characters per section
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
                # Cast the length to an integer to avoid type errors later
                template_structure.append((col, int(len(text_element))))

    return template_structure

# Enforce character limit for content sections
def enforce_character_limit(content, max_chars):
    # Ensure max_chars is treated as an integer
    max_chars = int(max_chars)
    relaxed_limit = max_chars + 20  # Relax the limit by 20 characters for flexibility
    if len(content) > relaxed_limit:
        truncated_content = content[:relaxed_limit].rsplit(' ', 1)[0]
        if not truncated_content:
            return content[:max_chars].rstrip() + "..."
        return truncated_content + "..."
    return content

# Build the content generation prompt based on the job details
def build_template_prompt(sheet_row, template_structure):
    job_id = sheet_row['Job ID']
    topic_description = sheet_row['Topic-Description']

    if not (job_id and topic_description and template_structure):
        return None, None

    # Construct the prompt based on job description and template structure
    prompt = f"Generate content for Job ID {job_id} using the description from the Google Sheet:\n\n"
    prompt += f"Description:\n{topic_description}\n\n"
    prompt += "Follow the exact template and section structure below, dividing umbrella sections verbatim into distinct subsections. Do not introduce any new or irrelevant content. Stay within character limits.\n\n"

    umbrella_sections = {}
    for section_name, content in template_structure:
        max_chars = content  # This is already an integer, no need for len()
        if '-' not in section_name:
            umbrella_sections[section_name] = section_name
            prompt += f"{section_name}: Stay within {max_chars} characters. Generate text strictly based on the Google Sheet description.\n"
        else:
            umbrella_key = section_name.split('-')[0]
            if umbrella_key in umbrella_sections:
                prompt += f"{section_name}: Extract a distinct, verbatim part of '{umbrella_sections[umbrella_key]}' within {max_chars} characters.\n"

    return prompt, job_id

# Generate content based on the prompt and enforce section limits
def generate_and_split_content(prompt, job_id, section_limits, retries=3, delay=5):
    for i in range(retries):
        try:
            message = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=1000,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            
            if message.content and len(message.content) > 0:
                content = message.content[0].text
            else:
                content = "No content generated."

            content_clean = clean_text(content)
            
            # Split and enforce character limits based on template structure
            structured_content = {}
            for section_name, max_chars in section_limits.items():
                section_content = enforce_character_limit(content_clean, max_chars)
                structured_content[section_name] = section_content

                # Apply umbrella structure to subsections
                if '-' in section_name:
                    first_part, second_part = split_content_into_umbrella(section_content)
                    structured_content[f"{section_name}-1"] = first_part
                    structured_content[f"{section_name}-2"] = second_part

            return structured_content
        
        except anthropic.APIError as e:
            st.warning(f"Error generating content for Job ID {job_id}. Retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
            time.sleep(delay)

    return None

# Split content into two halves for umbrella structure
def split_content_into_umbrella(content):
    words = content.split()
    midpoint = len(words) // 2
    first_half = " ".join(words[:midpoint])
    second_half = " ".join(words[midpoint:])
    return first_half, second_half

# Map generated content to the appropriate Google Sheet columns
def map_content_to_google_sheet(sheet, row_index, structured_content):
    mapping = {
        "Text01": "H", "Text01-1": "I", "Text01-2": "J", "Text01-3": "K", "Text01-4": "L", "01BG-Theme-Text": "M",
        "Text02": "N", "Text02-1": "O", "Text02-2": "P", "Text02-3": "Q", "Text02-4": "R", "02BG-Theme-Text": "S",
        "Text03": "T", "Text03-1": "U", "Text03-2": "V", "Text03-3": "W", "Text03-4": "X", "03BG-Theme-Text": "Y",
        "Text04": "Z", "Text04-1": "AA", "Text04-2": "AB", "Text04-3": "AC", "Text04-4": "AD", "04BG-Theme-Text": "AE",
        "Text05": "AF", "Text05-1": "AG", "Text05-2": "AH", "Text05-3": "AI", "Text05-4": "AJ", "05BG-Theme-Text": "AK",
        "CTA-Text": "AL", "CTA-Text-1": "AM", "CTA-Text-2": "AN", "Tagline-Text": "AO"
    }

    for section, content in structured_content.items():
        if section in mapping:
            col_letter = mapping[section]
            sheet.update_acell(f'{col_letter}{row_index}', content)
            time.sleep(1)

# Update the Google Sheet with generated content
def update_google_sheet_with_generated_content(sheet_id, job_id, generated_content):
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

# Main function
def main():
    st.title("AI Script Generator with Template Enforced Content")
    st.markdown("---")

    sheet_id = '1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8'
    request_sheet_id = '1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8'

    sheet_data = load_google_sheet(request_sheet_id)
    examples_data = load_examples()

    if sheet_data.empty or examples_data.empty:
        st.error("No data available from the request Google Sheet or the examples CSV.")
        return

    st.dataframe(sheet_data)

    if 'generated_contents' not in st.session_state:
        st.session_state['generated_contents'] = []

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

            generated_content = generate_and_split_content(prompt, job_id, dict(template_structure))

            if generated_content:
                update_google_sheet_with_generated_content(sheet_id, job_id, generated_content)

if __name__ == "__main__":
    main()
