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

def split_content_umbrella(content):
    """
    Improved splitting method based on clear word or sentence boundaries.
    Splits content based on logical breaks for umbrella structure.
    """
    content_parts = content.split('. ')
    if len(content_parts) > 1:
        # First part (umbrella start), second part (continuation)
        part1 = content_parts[0].strip()
        part2 = ' '.join(content_parts[1:]).strip()
    else:
        part1 = content.strip()
        part2 = ""
    
    return part1, part2

# Generate content and split based on umbrella model
def generate_and_split_content(prompt, job_id, retries=3, delay=5):
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
            st.warning(f"Error generating content for Job ID {job_id}. Retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
            time.sleep(delay)

    return None

def map_content_to_google_sheet(sheet, row_index, content_sections):
    """
    Map each generated section to its corresponding Google Sheet column.
    """
    mapping = {
        "Text01": "H", "Text01-1": "I", "Text01-2": "J", "Text01-3": "K", "Text01-4": "L", "01BG-Theme-Text": "M",
        "Text02": "N", "Text02-1": "O", "Text02-2": "P", "Text02-3": "Q", "Text02-4": "R", "02BG-Theme-Text": "S",
        "Text03": "T", "Text03-1": "U", "Text03-2": "V", "Text03-3": "W", "Text03-4": "X", "03BG-Theme-Text": "Y",
        "Text04": "Z", "Text04-1": "AA", "Text04-2": "AB", "Text04-3": "AC", "Text04-4": "AD", "04BG-Theme-Text": "AE",
        "Text05": "AF", "Text05-1": "AG", "Text05-2": "AH", "Text05-3": "AI", "Text05-4": "AJ", "05BG-Theme-Text": "AK",
        "CTA-Text": "AL", "CTA-Text-1": "AM", "CTA-Text-2": "AN", "Tagline-Text": "AO"
    }

    for section, content in content_sections.items():
        if section in mapping:
            col_letter = mapping[section]
            sheet.update_acell(f'{col_letter}{row_index}', content)
            time.sleep(1)

# Build the prompt using the selected template and job details
def build_template_prompt(sheet_row):
    job_id = sheet_row['Job ID']
    topic_description = sheet_row['Topic-Description']

    prompt = f"Generate content for Job ID {job_id} based on the theme:\n\n{topic_description}\n\n"
    prompt += "Generate 5 umbrella sections of content and divide each into two parts.\n"
    
    return prompt, job_id

def update_google_sheet_with_generated_content(sheet_id, job_id, generated_content):
    credentials_info = st.secrets["google_credentials"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    
    sheet = gc.open_by_key(sheet_id).sheet1
    rows = sheet.get_all_values()

    for i, row in enumerate(rows):
        if row[1].strip().lower() == job_id:
            row_index = i + 1

            # Split content for each section using umbrella splitting logic
            content_sections = {}
            for idx in range(1, 6):
                section_title = f"Text{idx:02d}"
                full_text = generated_content.get(section_title, "")
                part1, part2 = split_content_umbrella(full_text)
                content_sections[section_title] = full_text
                content_sections[f"{section_title}-1"] = part1
                content_sections[f"{section_title}-2"] = part2

            # Map the generated content to the appropriate columns
            map_content_to_google_sheet(sheet, row_index, content_sections)

            st.success(f"Content for Job ID {job_id} successfully updated in the Google Sheet.")
            return True

    st.error(f"No matching Job ID found for '{job_id}' in the target sheet.")
    return False

# Main function
def main():
    st.title("AI Script and Social Media Content Generator")
    st.markdown("---")

    sheet_id = '1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8'
    request_sheet_id = '1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8'

    sheet_data = load_google_sheet(request_sheet_id)

    if sheet_data.empty:
        st.error("No data available from the request Google Sheet.")
        return

    st.dataframe(sheet_data)

    if st.button("Generate Content"):
        for idx, row in sheet_data.iterrows():
            if not row['Job ID']:
                st.warning(f"Row {idx + 1} is missing Job ID. Skipping this row.")
                continue

            job_id = row['Job ID']
            prompt, job_id = build_template_prompt(row)

            generated_content = generate_and_split_content(prompt, job_id)

            if generated_content:
                update_google_sheet_with_generated_content(sheet_id, job_id, generated_content)

if __name__ == "__main__":
    main()
