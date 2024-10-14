import streamlit as st
import pandas as pd
import re
import anthropic
from google.oauth2.service_account import Credentials
import gspread
import time
from collections import defaultdict

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

def load_google_sheet(sheet_id):
    credentials_info = st.secrets["google_credentials"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(
        credentials_info, scopes=scopes
    )
    gc = gspread.authorize(credentials)
    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        data = sheet.get_all_values()
        headers = data[0]
        header_counts = defaultdict(int)
        new_headers = []
        for h in headers:
            count = header_counts[h]
            if count > 0:
                new_h = f"{h}_{count}"
            else:
                new_h = h
            new_headers.append(new_h)
            header_counts[h] +=1
        rows = data[1:]
        df = pd.DataFrame(rows, columns=new_headers)
        return df
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
    for col in example_row.columns:
        if col != 'Template':
            text_element = example_row[col].values[0]
            if pd.notna(text_element):
                template_structure.append((col, text_element))
    return template_structure

def build_template_prompt(topic_description, template_structure):
    if not (topic_description and template_structure):
        return None

    prompt = f"{anthropic.HUMAN_PROMPT}Using the following description, generate content for each section as specified. Each section should start with 'Section [Section Name]:' followed by the content. Use the description to generate content for each section, and stay within the specified character limits.\n\n"
    prompt += f"Description:\n{topic_description}\n\n"

    for section_name, content in template_structure:
        max_chars = len(content)
        prompt += f"Section {section_name}: Content (max {max_chars} characters)\n"

    prompt += "\nPlease provide the content for each section as specified, starting each with 'Section [Section Name]:'.\n" + anthropic.AI_PROMPT

    return prompt

def generate_content_with_retry(prompt, retries=3, delay=5):
    for i in range(retries):
        try:
            response = client.completions.create(
                prompt=prompt,
                model="claude-2",
                max_tokens_to_sample=1000,
                temperature=0.7,
            )

            content = response.completion if response.completion else "No content generated."

            content_clean = clean_text(content)

            sections = {}
            current_section = None
            for line in content_clean.split('\n'):
                if line.strip().startswith("Section "):
                    current_section = line.split(":")[0].replace("Section ", "").strip()
                    sections[current_section] = ""
                    if ":" in line:
                        line_content = line.split(":", 1)[1].strip()
                        sections[current_section] += line_content + "\n"
                elif current_section:
                    sections[current_section] += line + "\n"

            for section in sections:
                sections[section] = sections[section].strip()

            return sections

        except anthropic.ApiException as e:
            if 'overloaded' in str(e).lower() and i < retries - 1:
                st.warning(f"API is overloaded, retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
                time.sleep(delay)
            else:
                st.error(f"Error generating content: {e}")
                return None

def generate_social_content_with_retry(main_content, selected_channels, retries=3, delay=5):
    generated_content = {}
    for channel in selected_channels:
        for i in range(retries):
            try:
                prompt = f"{anthropic.HUMAN_PROMPT}Generate a {channel.capitalize()} post based on this content:\n{main_content}\n\n{anthropic.AI_PROMPT}"
                response = client.completions.create(
                    prompt=prompt,
                    model="claude-2",
                    max_tokens_to_sample=500,
                    temperature=0.7,
                )

                content = response.completion if response.completion else "No content generated."
                generated_content[channel] = content
                break

            except anthropic.ApiException as e:
                if 'overloaded' in str(e).lower() and i < retries - 1:
                    st.warning(f"API is overloaded for {channel}, retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
                    time.sleep(delay)
                else:
                    st.error(f"Error generating {channel} content: {e}")
        else:
            generated_content[channel] = ""
    return generated_content

def update_google_sheet(sheet_id, job_id, generated_content):
    credentials_info = st.secrets["google_credentials"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(
        credentials_info, scopes=scopes
    )
    gc = gspread.authorize(credentials)

    try:
        sheet = gc.open_by_key(sheet_id).sheet1

        cell = sheet.find(job_id, in_column=2)
        if not cell:
            st.warning(f"Job ID {job_id} not found in the sheet.")
            return

        row = cell.row

        headers = sheet.row_values(1)
        header_to_col = {}
        header_counts = defaultdict(int)
        for idx, h in enumerate(headers):
            count = header_counts[h]
            if count > 0:
                new_h = f"{h}_{count}"
            else:
                new_h = h
            header_counts[h] +=1
            header_to_col[new_h] = idx +1  # 1-based indexing

        for section, content in generated_content.items():
            if section in header_to_col:
                col = header_to_col[section]
                sheet.update_cell(row, col, content)
            else:
                st.warning(f"Section {section} not found in sheet headers.")
        st.success(f"Updated Google Sheet for Job ID {job_id}")
    except Exception as e:
        st.error(f"Error updating Google Sheet: {e}")

def get_column_name(df, name):
    cols = [col for col in df.columns if col == name or col.startswith(name + '_')]
    if cols:
        return cols[0]
    else:
        return None

def main():
    st.title("AI Script Generator from Google Sheets and Templates")
    st.markdown("---")

    # Load data from the request sheet (input data)
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
        job_id_col = get_column_name(sheet_data, 'Job ID')
        selected_template_col = get_column_name(sheet_data, 'Selected-Template')
        topic_description_col = get_column_name(sheet_data, 'Topic-Description')

        if not all([job_id_col, selected_template_col, topic_description_col]):
            st.error("Required columns ('Job ID', 'Selected-Template', 'Topic-Description') not found in the sheet.")
            return

        for idx, row in sheet_data.iterrows():
            job_id = row[job_id_col]
            selected_template = row[selected_template_col]
            topic_description = row[topic_description_col]

            if not (job_id and selected_template and topic_description):
                st.warning(f"Row {idx + 1} is missing Job ID, Selected-Template, or Topic-Description. Skipping this row.")
                continue
            template_structure = extract_template_structure(selected_template, examples_data)
            if template_structure is None:
                st.warning(f"Template {selected_template} not found in examples data.")
                continue
            prompt = build_template_prompt(topic_description, template_structure)

            if not prompt:
                continue

            generated_content = generate_content_with_retry(prompt)
            if generated_content:
                generated_contents.append((job_id, generated_content))

                # Update the response sheet with generated content
                update_google_sheet('1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8', job_id, generated_content)

        st.session_state['generated_contents'] = generated_contents

        for job_id, content in generated_contents:
            st.subheader(f"Generated Content for Job ID: {job_id}")
            for section, text in content.items():
                st.text_area(f"Section {section}", text, height=100, key=f"text_area_{job_id}_{section}")
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
