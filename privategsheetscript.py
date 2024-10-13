import streamlit as st
import pandas as pd
import re
import anthropic
from google.oauth2.service_account import Credentials
import gspread
import time

# Initialize the Anthropic client
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

# Load Google Sheet
def load_google_sheet(sheet_id):
    credentials_info = st.secrets["google_credentials"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        data = pd.DataFrame(sheet.get_all_records())
        return data, sheet
    except gspread.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found.")
        return pd.DataFrame(), None

# Load examples from CSV
@st.cache_data
def load_examples():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    try:
        examples = pd.read_csv(url)
        return examples
    except Exception as e:
        st.error(f"Error loading examples CSV: {e}")
        return pd.DataFrame()

# Clean text content
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

# Extract template structure from examples CSV
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

# Build template prompt for generation
def build_template_prompt(sheet_row, template_structure):
    job_id = sheet_row['Job ID']
    topic_description = sheet_row['Topic-Description']

    if not (job_id and topic_description and template_structure):
        return None, None

    prompt = f"Generate content for Job ID {job_id} using the description from the Google Sheet. Follow the section structure exactly as given, ensuring that the content of the umbrella sections is divided **verbatim** into subsections.\n\n"
    
    prompt += f"Description from Google Sheet:\n{topic_description}\n\n"
    prompt += "For each section, generate content **in strict order**. Subsections must split the umbrella section **verbatim** into distinct, meaningful parts. **Do not reorder sections or introduce new content**.\n\n"

    umbrella_sections = {}
    for section_name, content in template_structure:
        max_chars = len(content)
        if '-' not in section_name:
            umbrella_sections[section_name] = section_name
            prompt += f"Section {section_name}: Generate content based only on the description from the Google Sheet. Stay within {max_chars} characters.\n"
        else:
            umbrella_key = section_name.split('-')[0]
            if umbrella_key in umbrella_sections:
                prompt += f"Section {section_name}: Extract a **distinct, verbatim part** of the umbrella section '{umbrella_sections[umbrella_key]}'. Ensure that subsections are ordered logically and **no new content is introduced**.\n"

    if 'CTA-Text' in [section for section, _ in template_structure]:
        prompt += "Ensure a clear call-to-action (CTA-Text) is provided at the end of the content."

    prompt += "\nStrictly generate content for every section, ensuring subsections extract distinct, verbatim parts from the umbrella content in proper order."

    return prompt, job_id

# Generate content with retries
def generate_content_with_retry(prompt, job_id, retries=3, delay=5):
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
            return content_clean
        
        except anthropic.APIError as e:
            if e.error.get('type') == 'overloaded_error' and i < retries - 1:
                st.warning(f"API is overloaded, retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
                time.sleep(delay)
            else:
                st.error(f"Error generating content: {e}")
                return None

# Map generated content to Google Sheet cells
def map_generated_content_to_cells(sheet, job_id, generated_content, template_structure):
    job_id_normalized = job_id.strip().lower()
    rows = sheet.get_all_values()

    # Define column mappings for each section
    column_mappings = {
        "Text01": "H", "Text01-1": "I", "Text01-2": "J", "Text01-3": "K", "Text01-4": "L", "01BG-Theme-Text": "M",
        "Text02": "N", "Text02-1": "O", "Text02-2": "P", "Text02-3": "Q", "Text02-4": "R", "02BG-Theme-Text": "S",
        "Text03": "T", "Text03-1": "U", "Text03-2": "V", "Text03-3": "W", "Text03-4": "X", "03BG-Theme-Text": "Y",
        "Text04": "Z", "Text04-1": "AA", "Text04-2": "AB", "Text04-3": "AC", "Text04-4": "AD", "04BG-Theme-Text": "AE",
        "Text05": "AF", "Text05-1": "AG", "Text05-2": "AH", "Text05-3": "AI", "Text05-4": "AJ", "05BG-Theme-Text": "AK",
        "CTA-Text": "AL", "CTA-Text-1": "AM", "CTA-Text-2": "AN", "Tagline-Text": "AO"
    }

    st.write(f"Processing Job ID: {job_id}")

    # Iterate over all rows to find the matching Job ID
    for i, row in enumerate(rows):
        job_id_in_sheet = row[1].strip().lower() if row[1].strip() else None
        if job_id_in_sheet == job_id_normalized:
            row_index = i + 1

            # Ensure the generated_content is structured properly for updating
            for section_name, _ in template_structure:
                content = generated_content.get(section_name, "").strip()
                if content:
                    col_letter = column_mappings.get(section_name)
                    if col_letter:
                        st.write(f"Updating cell {col_letter}{row_index} with content: {content}")
                        try:
                            sheet.update_acell(f'{col_letter}{row_index}', content)
                        except Exception as e:
                            st.error(f"Failed to update cell {col_letter}{row_index}: {e}")
                        time.sleep(1)  # To avoid rate-limiting
            break
            
# Main function
def main():
    st.title("AI Script Generator with Google Sheets Transfer")
    st.markdown("---")

    sheet_id = '1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8'
    request_sheet_id = '1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8'

    sheet_data, sheet = load_google_sheet(request_sheet_id)
    examples_data = load_examples()

    if sheet_data.empty or examples_data.empty:
        st.error("No data available from Google Sheets or Templates CSV.")
        return

    st.dataframe(sheet_data)

    if st.button("Generate and Transfer Content"):
        for idx, row in sheet_data.iterrows():
            if not (row['Job ID'] and row['Selected-Template'] and row['Topic-Description']):
                st.warning(f"Row {idx + 1} is missing Job ID, Selected-Template, or Topic-Description. Skipping this row.")
                continue

            template_structure = extract_template_structure(row['Selected-Template'], examples_data)
            if template_structure is None:
                st.warning(f"No template structure found for {row['Selected-Template']}.")
                continue

            prompt, job_id = build_template_prompt(row, template_structure)
            if not prompt:
                st.warning(f"Failed to build prompt for Job ID {row['Job ID']}.")
                continue

            generated_content = generate_content_with_retry(prompt, row['Job ID'])
            if generated_content:
                st.text_area(f"Generated Content for Job ID {job_id}", generated_content)
                map_generated_content_to_cells(sheet, row['Job ID'], generated_content, template_structure)

if __name__ == "__main__":
    main()
