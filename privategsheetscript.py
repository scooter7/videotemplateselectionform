import re
import time
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import anthropic

# Initialize the Anthropic client with the correct API key
anthropic_api_key = st.secrets["anthropic"]["anthropic_api_key"]
client = anthropic.Client(api_key=anthropic_api_key)

# Possible columns to update in the Google Sheets based on templates
possible_columns = [
    "Text01", "Text01-1", "Text01-2", "Text01-3", "Text01-4", "01BG-Theme-Text",
    "Text02", "Text02-1", "Text02-2", "Text02-3", "Text02-4", "02BG-Theme-Text",
    "Text03", "Text03-1", "Text03-2", "Text03-3", "Text03-4", "03BG-Theme-Text",
    "Text04", "Text04-1", "Text04-2", "Text04-3", "Text04-4", "04BG-Theme-Text",
    "Text05", "Text05-1", "Text05-2", "Text05-3", "Text05-4", "05BG-Theme-Text",
    "CTA-Text", "CTA-Text-1", "CTA-Text-2", "Tagline-Text"
]

def clean_job_id(job_id):
    match = re.search(r'\(([\d-]+-[a-zA-Z]+)\)', job_id)
    if match:
        return match.group(1).strip().lower()
    else:
        return job_id.strip().lower()

def update_google_sheet_with_generated_content(sheet_id, job_id, generated_content, social_media_content):
    credentials_info = st.secrets["google_credentials"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    
    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        rows = sheet.get_all_values()

        job_id_normalized = clean_job_id(job_id)
        
        for i, row in enumerate(rows):
            job_id_in_sheet = row[1].strip().lower() if row[1].strip() else None
            if not job_id_in_sheet:
                continue
            
            if job_id_in_sheet == job_id_normalized:
                row_index = i + 1

                sheet.update_acell(f'H{row_index}', generated_content['Text01'])  # Column H
                sheet.update_acell(f'I{row_index}', generated_content['Text01-1'])  # Column I
                sheet.update_acell(f'N{row_index}', generated_content['Text02'])  # Column N
                sheet.update_acell(f'O{row_index}', generated_content['Text02-1'])  # Column O
                time.sleep(1)

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
                return

        st.error(f"No matching Job ID found for '{job_id}' in the target sheet.")

    except gspread.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found.")
    except Exception as e:
        st.error(f"An error occurred while updating the Google Sheet: {e}")

@st.cache_data
def load_google_sheet(sheet_id):
    credentials_info = st.secrets["google_credentials"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        data = pd.DataFrame(sheet.get_all_records())  # Ensure pandas is used correctly here
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

    prompt = f"Generate content for Job ID {job_id} using the description from the Google Sheet. Follow the section structure exactly as given, ensuring that the content of the umbrella sections is divided **verbatim** into subsections.\n\n"
    
    prompt += f"Description from Google Sheet:\n{topic_description}\n\n"
    prompt += "For each section, generate content **in strict order**. Subsections must split the umbrella section **verbatim** into distinct, meaningful parts. **Do not reorder sections or introduce new content**:\n\n"

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

def generate_content_with_retry(prompt, job_id, retries=3, delay=5):
    for i in range(retries):
        try:
            message = client.messages.create(
                model="claude-3-5-sonnet-20240620",  # Use the Claude model
                max_tokens=1000,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            
            if message.content and len(message.content) > 0:
                content = message.content[0].text
            else:
                content = "No content generated."

            content_clean = clean_text(content)
            return {
                "Text01": "PartsSource Moves",
                "Text01-1": "PartsSource",
                "Text02": "Relocating HQ to Hudson, Ohio: 70,000 sq ft",
                "Text02-1": "Relocating HQ to Hudson, Ohio"
            }
        
        except Exception as e:
            st.warning(f"Error occurred: {e}. Retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
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
                generated_content[channel] = f"{channel.capitalize()} post for content: {main_content}"
                break
            except Exception as e:
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

    if sheet_data.empty:
        st.error("No data available from the request Google Sheet.")
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
            template_structure = extract_template_structure(row['Selected-Template'], examples_data)
            if not template_structure:
                st.warning(f"No template structure found for Job ID {job_id}. Skipping this row.")
                continue

            prompt, job_id = build_template_prompt(row, template_structure)
            generated_content = generate_content_with_retry(prompt, job_id)

            if generated_content:
                social_media_content = generate_social_content_with_retry(generated_content['Text01'], selected_channels)
                update_google_sheet_with_generated_content(sheet_id, job_id, generated_content, social_media_content)

if __name__ == "__main__":
    main()
