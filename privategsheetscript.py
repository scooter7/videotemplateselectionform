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

possible_columns = [
    "Text01", "Text01-1", "Text01-2", "Text01-3", "Text01-4", "01BG-Theme-Text",
    "Text02", "Text02-1", "Text02-2", "Text02-3", "Text02-4", "02BG-Theme-Text",
    "Text03", "Text03-1", "Text03-2", "Text03-3", "Text03-4", "03BG-Theme-Text",
    "Text04", "Text04-1", "Text04-2", "Text04-3", "Text04-4", "04BG-Theme-Text",
    "Text05", "Text05-1", "Text05-2", "Text05-3", "Text05-4", "05BG-Theme-Text",
    "CTA-Text", "CTA-Text-1", "CTA-Text-2", "Tagline-Text"
]

def clean_job_id(job_id):
    return job_id.strip().lower() if job_id else None

# Update Google Sheet with generated content and social media content
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
            if job_id_in_sheet == job_id_normalized:
                row_index = i + 1

                # Update relevant columns in the sheet
                sheet.update_acell(f'H{row_index}', generated_content.get('Text01', ''))
                sheet.update_acell(f'I{row_index}', generated_content.get('Text01-1', ''))
                sheet.update_acell(f'N{row_index}', generated_content.get('Text02', ''))
                sheet.update_acell(f'O{row_index}', generated_content.get('Text02-1', ''))
                time.sleep(1)

                # Update social media content if present
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
        st.error(f"No matching Job ID found for '{job_id}' in the sheet.")
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
            st.error(f"Error updating Google Sheet: {e.response.json()}")
            return False

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
def load_examples():
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
    template_number_str = selected_template.split('_')[-1] if "template_SH_" in selected_template else "01"
    example_row = examples_data[examples_data['Template'] == f'template_SH_{template_number_str}']
    
    if example_row.empty:
        return None

    template_structure = []
    for col in example_row.columns:
        text_element = example_row[col].values[0]
        if pd.notna(text_element):
            template_structure.append((col, text_element))

    return template_structure

def build_template_prompt(sheet_row, template_structure):
    job_id = sheet_row['Job ID']
    topic_description = sheet_row['Topic-Description']

    if not (job_id and topic_description and template_structure):
        return None, None

    prompt = f"\n\nHuman: Generate content for Job ID {job_id} based on the theme:\n\n{topic_description}\n\n"
    prompt += "For each section, generate content according to the following structure:\n\n"

    for section_name, content in template_structure:
        max_chars = len(content)
        prompt += f"{section_name}: {max_chars} characters limit.\n"

    return prompt, job_id

def generate_content_with_retry(prompt, job_id, retries=3, delay=5):
    if not isinstance(prompt, str) or not prompt.strip():
        st.error(f"Invalid prompt for Job ID {job_id}. Skipping generation.")
        return None
    
    for i in range(retries):
        try:
            message = client.completions.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens_to_sample=1000,
                temperature=0.7,
                prompt=prompt
            )
            
            if message['completion'] and len(message['completion']) > 0:
                content = message['completion']
            else:
                content = "No content generated."

            content_clean = clean_text(content)
            return {
                "Text01": content_clean[:100],
                "Text01-1": content_clean[100:200],
                "Text02": content_clean[200:300],
                "Text02-1": content_clean[300:400]
            }
        
        except anthropic.APIError as e:
            st.warning(f"Error: {e}. Retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
            time.sleep(delay)

    return None

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
                message = client.completions.create(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens_to_sample=500,
                    temperature=0.7,
                    prompt=prompt
                )
                
                if message['completion'] and len(message['completion']) > 0:
                    generated_content[channel] = message['completion']
                break
            
            except anthropic.APIError as e:
                st.warning(f"Error generating {channel} content: {e}. Retrying...")
                time.sleep(delay)
    
    return generated_content

def main():
    st.title("AI Script and Social Media Content Generator")
    st.markdown("---")

    sheet_id = '1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8'
    request_sheet_id = '1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8'

    sheet_data = load_google_sheet(request_sheet_id)
    examples_data = load_examples()

    if sheet_data.empty or examples_data.empty:
        st.error("No data available from the request Google Sheet or the examples CSV.")
        return

    st.dataframe(sheet_data)

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

            generated_content = generate_content_with_retry(prompt, job_id)

            if generated_content:
                social_media_content = generate_social_content_with_retry(generated_content['Text01'], selected_channels)
                update_google_sheet_with_generated_content(sheet_id, job_id, generated_content, social_media_content)

if __name__ == "__main__":
    main()
