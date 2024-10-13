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

# Extract the template structure and max characters per section from the CSV
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

    # Return a dictionary with column names and their character limits
    template_structure = {}
    for col in example_row.columns:
        text_element = example_row[col].values[0]
        if pd.notna(text_element):
            template_structure[col] = len(text_element)

    return template_structure

def build_template_prompt(sheet_row, template_structure):
    job_id = sheet_row['Job ID']
    topic_description = sheet_row['Topic-Description']

    if not (job_id and topic_description and template_structure):
        return None, None

    prompt = f"Generate content for Job ID {job_id} based on the theme:\n\n{topic_description}\n\n"
    prompt += "Follow the template structure strictly. Each section should be generated in the exact order and divided into subsections as follows:\n\n"

    for section_name, max_chars in template_structure.items():
        prompt += f"{section_name}: Limit to {max_chars} characters.\n"

    return prompt, job_id

# Function to split the generated content into sections and subsections
def split_content_into_subsections(content, section_limits):
    words = content.split()
    subsections = {}
    word_idx = 0

    for section, max_chars in section_limits.items():
        section_content = []
        char_count = 0
        
        while word_idx < len(words) and (char_count + len(words[word_idx]) + 1) <= max_chars:
            section_content.append(words[word_idx])
            char_count += len(words[word_idx]) + 1
            word_idx += 1

        subsections[section] = " ".join(section_content).strip()

    return subsections

# Generate content and split it based on the template structure
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
            structured_content = split_content_into_subsections(content_clean, section_limits)

            return structured_content
        
        except anthropic.APIError as e:
            st.warning(f"Error generating content for Job ID {job_id}. Retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
            time.sleep(delay)

    return None

# Map structured content to Google Sheet cells based on the umbrella model
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

def generate_social_content_with_retry(main_content, selected_channels, retries=3, delay=5):
    social_prompts = {
        "facebook": f"Generate a Facebook post based on this content:\n{main_content}",
        "linkedin": f"Generate a LinkedIn post based on this content:\n{main_content}",
        "instagram": f"Generate an Instagram post based on this content:\n{main_content}"
    }
    
    generated_content = {}
    
    for channel in selected_channels:
        for i in range(retries):
            try:
                prompt = social_prompts[channel]
                
                message = client.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=500,
                    temperature=0.7,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                if message.content and len(message.content) > 0:
                    generated_content[channel] = message.content[0].text
                break
            
            except anthropic.APIError as e:
                st.warning(f"Error generating {channel} content: {e}. Retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
                time.sleep(delay)
    
    return generated_content

def update_google_sheet_with_generated_content(sheet_id, job_id, generated_content, social_media_content, retries=3):
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

                if social_media_content:
                    sm_columns = {
                        "LinkedIn-Post-Content-Reco": 'BU',
                        "Facebook-Post-Content-Reco": 'BV',
                        "Instagram-Post-Content-Reco": 'BW',
                        "YouTube-Post-Content-Reco": 'BX',
                        "Blog-Post-Content-Reco": 'BY',
                        "Email-Post-Content-Reco": 'BZ'
                    }
                    for channel, content in social_media_content.items():
                        if channel in sm_columns:
                            col_letter = sm_columns[channel]
                            sheet.update_acell(f'{col_letter}{row_index}', content)
                            time.sleep(1)
                
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
            return update_google_sheet_with_generated_content(sheet_id, job_id, generated_content, social_media_content, retries-1)
        else:
            st.error(f"An error occurred while updating the Google Sheet: {e.response.json()}")
            return False

def main():
    st.title("AI Script and Social Media Content Generator")
    st.markdown("---")

    sheet_id = '1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8'
    request_sheet_id = '1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8'

    sheet_data = load_google_sheet(request_sheet_id)
    examples_data = load_template_csv()

    if sheet_data.empty or examples_data.empty:
        st.error("No data available from the request Google Sheet or the examples CSV.")
        return

    st.dataframe(sheet_data)

    if 'generated_contents' not in st.session_state:
        st.session_state['generated_contents'] = []

    selected_channels = st.multiselect("Select social media channels to generate content for:", 
                                       ["facebook", "linkedin", "instagram"])

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

            generated_content = generate_and_split_content(prompt, job_id, template_structure)

            if generated_content:
                social_media_content = generate_social_content_with_retry(generated_content['Text01'], selected_channels)
                update_google_sheet_with_generated_content(sheet_id, job_id, generated_content, social_media_content)

if __name__ == "__main__":
    main()
