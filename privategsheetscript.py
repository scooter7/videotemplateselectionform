import streamlit as st
import pandas as pd
import re
import anthropic
from google.oauth2.service_account import Credentials
import gspread
import time

anthropic_api_key = st.secrets["anthropic"]["anthropic_api_key"]
client = anthropic.Client(api_key=anthropic_api_key)

st.markdown(
    """
    <style>
    .st-emotion-cache-12fmjuu.ezrtsby2 {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <style>
    .logo-container {
        display: flex;
        justify-content: center;
        align-items: center;
        margin-bottom: 20px;
    }
    .logo-container img {
        width: 600px;
    }
    .app-container {
        border-left: 5px solid #58258b;
        border-right: 5px solid #58258b;
        padding-left: 15px;
        padding-right: 15px;
    }
    .stTextArea, .stTextInput, .stMultiSelect, .stSlider {
        color: #42145f;
    }
    .stButton button {
        background-color: #fec923;
        color: #42145f;
    }
    .stButton button:hover {
        background-color: #42145f;
        color: #fec923;
    }
    </style>
    """,
    unsafe_allow_html=True
)

possible_columns = [
    "Text01", "Text01-1", "Text01-2", "Text01-3", "Text01-4", "01BG-Theme-Text",
    "Text02", "Text02-1", "Text02-2", "Text02-3", "Text02-4", "02BG-Theme-Text",
    "Text03", "Text03-1", "Text03-2", "Text03-3", "Text03-4", "03BG-Theme-Text",
    "Text04", "Text04-1", "Text04-2", "Text04-3", "Text04-4", "04BG-Theme-Text",
    "Text05", "Text05-1", "Text05-2", "Text05-3", "Text05-4", "05BG-Theme-Text",
    "CTA-Text", "CTA-Text-1", "CTA-Text-2", "Tagline-Text"
]

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

def enforce_character_limit(content, max_chars):
    relaxed_limit = max_chars + 20
    if len(content) > relaxed_limit:
        truncated_content = content[:relaxed_limit].rsplit(' ', 1)[0]
        if not truncated_content:
            return content[:max_chars].rstrip() + "..."
        return truncated_content + "..."
    return content

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

def generate_content_with_retry(prompt, job_id, template_structure, retries=3, delay=5):
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
            
            sections = {}
            current_section = None
            for line in content_clean.split('\n'):
                if line.strip().startswith("Section "):
                    current_section = line.split(":")[0].replace("Section ", "").strip()
                    sections[current_section] = ""
                elif current_section:
                    sections[current_section] += line + "\n"
            
            for section in sections:
                sections[section] = sections[section].strip()
            
            return sections
        
        except anthropic.APIError as e:
            if e.error.get('type') == 'overloaded_error' and i < retries - 1:
                st.warning(f"API is overloaded, retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
                time.sleep(delay)
            else:
                st.error(f"Error generating content: {e}")
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
                if e.error.get('type') == 'overloaded_error' and i < retries - 1:
                    st.warning(f"API is overloaded for {channel}, retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
                    time.sleep(delay)
                else:
                    st.error(f"Error generating {channel} content: {e}")
    return generated_content

def update_google_sheet(sheet_id, job_id, generated_content):
    credentials_info = st.secrets["google_credentials"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    
    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        
        cell = sheet.find(job_id, in_column=2)
        if not cell:
            st.warning(f"Job ID {job_id} not found in the sheet.")
            return
        
        row = cell.row
        
        section_to_column = {
            "Text01": "H", "Text01-1": "I", "Text01-2": "J", "Text01-3": "K", "Text01-4": "L", "01BG-Theme-Text": "M",
            "Text02": "N", "Text02-1": "O", "Text02-2": "P", "Text02-3": "Q", "Text02-4": "R", "02BG-Theme-Text": "S",
            "Text03": "T", "Text03-1": "U", "Text03-2": "V", "Text03-3": "W", "Text03-4": "X", "03BG-Theme-Text": "Y",
            "Text04": "Z", "Text04-1": "AA", "Text04-2": "AB", "Text04-3": "AC", "Text04-4": "AD", "04BG-Theme-Text": "AE",
            "Text05": "AF", "Text05-1": "AG", "Text05-2": "AH", "Text05-3": "AI", "Text05-4": "AJ", "05BG-Theme-Text": "AK",
            "CTA-Text": "AL", "CTA-Text-1": "AM", "CTA-Text-2": "AN", "Tagline-Text": "AO"
        }
        
        updates = []
        for section, content in generated_content.items():
            if section in section_to_column:
                col = gspread.utils.a1_to_rowcol(section_to_column[section] + '1')[1]
                updates.append({
                    'range': sheet.cell(row, col),
                    'values': [[content]]
                })
        
        if updates:
            sheet.batch_update(updates)
        
        st.success(f"Updated Google Sheet for Job ID {job_id}")
    except Exception as e:
        st.error(f"Error updating Google Sheet: {e}")

def main():
    st.title("AI Script Generator from Google Sheets and Templates")
    st.markdown("---")

    if 'sheet_data' not in st.session_state:
        st.session_state['sheet_data'] = load_google_sheet('1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8')
    if 'examples_data' not in st.session_state:
        st.session_state['examples_data'] = load_examples()

    sheet_data = st.session_state['sheet_data']
    examples_data = st.session_state['examples_data']

    if sheet_data.empty or examples_data.empty:
        st.error("No data available from Google Sheets or Templates CSV.")
        return

    st.dataframe(sheet_data)

    if 'generated_contents' not in st.session_state:
        st.session_state['generated_contents'] = []

    if st.button("Generate Content"):
        generated_contents = []
        for idx, row in sheet_data.iterrows():
            if not (row['Job ID'] and row['Selected-Template'] and row['Topic-Description']):
                st.warning(f"Row {idx + 1} is missing Job ID, Selected-Template, or Topic-Description. Skipping this row.")
                continue
            template_structure = extract_template_structure(row['Selected-Template'], examples_data)
            if template_structure is None:
                continue
            prompt, job_id = build_template_prompt(row, template_structure)

            if not prompt or not job_id:
                continue

            generated_content = generate_content_with_retry(prompt, job_id, template_structure)
            if generated_content:
                generated_contents.append((job_id, generated_content))
                
                update_google_sheet('1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8', job_id, generated_content)

        st.session_state['generated_contents'] = generated_contents
        
        for job_id, content in generated_contents:
            st.subheader(f"Generated Content for Job ID: {job_id}")
            for section, text in content.items():
                st.text_area(f"Section {section}", text, height=100)
            st.markdown("---")

    st.markdown("---")
    st.header("Generate Social Media Posts")
    
    if 'selected_channels' not in st.session_state:
        st.session_state['selected_channels'] = []

    facebook = st.checkbox("Facebook", value="facebook" in st.session_state['selected_channels'])
    linkedin = st.checkbox("LinkedIn", value="linkedin" in st.session_state['selected_channels'])
    instagram = st.checkbox("Instagram", value="instagram" in st.session_state['selected_channels'])

    selected_channels = []
    if facebook:
        selected_channels.append("facebook")
    if linkedin:
        selected_channels.append("linkedin")
    if instagram:
        selected_channels.append("instagram")
    
    st.session_state['selected_channels'] = selected_channels

    if selected_channels and 'generated_contents' in st.session_state:
        if 'social_media_contents' not in st.session_state:
            st.session_state['social_media_contents'] = []

        if st.button("Generate Social Media Content"):
            social_media_contents = []
            for job_id, generated_content in st.session_state['generated_contents']:
                combined_content = "\n".join([f"{section}: {content}" for section, content in generated_content.items()])
                social_content_for_row = generate_social_content_with_retry(combined_content, selected_channels)

                if social_content_for_row:
                    social_media_contents.append((job_id, social_content_for_row))
            
            st.session_state['social_media_contents'] = social_media_contents

    if 'social_media_contents' in st.session_state:
        for job_id, social_content in st.session_state['social_media_contents']:
            st.subheader(f"Generated Social Media Content for Job ID: {job_id}")
            for channel, content in social_content.items():
                st.subheader(f"{channel.capitalize()} Post")
                st.text_area(f"{channel.capitalize()} Content", content, height=200, key=f"{channel}_content_{job_id}")
                st.download_button(
                    label=f"Download {channel.capitalize()} Content",
                    data=content,
                    file_name=f"{channel}_post_{job_id}.txt",
                    mime="text/plain",
                    key=f"download_{channel}_{job_id}"
                )

    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
