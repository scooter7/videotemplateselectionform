import streamlit as st
import pandas as pd
import re
import anthropic
from google.oauth2.service_account import Credentials
import gspread
import time
from datetime import datetime
from collections import defaultdict

# Initialize Anthropics client
anthropic_api_key = st.secrets["anthropic"]["anthropic_api_key"]
client = anthropic.Anthropic(api_key=anthropic_api_key)

# Load Google Sheet
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
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        return df
    except gspread.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found.")
        return pd.DataFrame()

# Load examples data
@st.cache_data
def load_examples():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    try:
        examples = pd.read_csv(url)
        return examples
    except Exception as e:
        st.error(f"Error loading examples CSV: {e}")
        return pd.DataFrame()

# Clean text
def clean_text(text):
    text = re.sub(r'\*\*', '', text)
    emoji_pattern = re.compile(
        "[" 
        u"\U0001F600-\U0001F64F"  
        u"\U0001F300-\U0001F5FF"  
        u"\U0001F680-\U0001F6FF"  
        u"\U0001F1E0-\U0001F1FF"  
        u"\u2600-\u26FF"          
        u"\u2700-\u27BF"          
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text)

# Extract template structure
def extract_template_structure(selected_template, examples_data):
    example_row = examples_data[examples_data['Template'] == selected_template]
    if example_row.empty:
        return None
    template_structure = []
    for col in example_row.columns:
        if col != 'Template' and pd.notna(example_row[col].values[0]):
            text_element = example_row[col].values[0]
            max_chars = len(str(text_element))
            template_structure.append((col, text_element, max_chars))
    return template_structure

# Ensure all sections are populated
def ensure_all_sections_populated(generated_content, template_structure):
    for section_name, _, _ in template_structure:
        if section_name not in generated_content:
            generated_content[section_name] = ""
    return generated_content

# Build prompt from template
def build_template_prompt(topic_description, template_structure):
    if not (topic_description and template_structure):
        return None
    prompt = f"Using the following description, generate content for each main section as specified. Each main section should start with 'Section [Section Name]:' followed by the content. Ensure that the content for each section does not exceed the specified character limit.\n\n"
    prompt += f"Description:\n{topic_description}\n\n"
    for section_name, _, max_chars in template_structure:
        prompt += f"Section {section_name}: (max {max_chars} characters)\n"
    return prompt

# Generate content with retry
def generate_content_with_retry(prompt, section_character_limits, retries=3, delay=5):
    for i in range(retries):
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            if not response.content:
                continue
            content_clean = clean_text(response.content)
            sections = {}
            current_section = None
            for line in content_clean.split('\n'):
                line = line.strip()
                if line.startswith("Section "):
                    section_header = line.split(":", 1)
                    section_name = section_header[0].replace("Section ", "").strip()
                    section_content = section_header[1].strip() if len(section_header) > 1 else ""
                    current_section = section_name
                    sections[current_section] = section_content
                elif current_section:
                    sections[current_section] += ' ' + line.strip()
            for section in sections:
                limit = section_character_limits.get(section, None)
                if limit and len(sections[section]) > limit:
                    sections[section] = sections[section][:limit].rsplit(' ', 1)[0]
            return sections
        except Exception as e:
            if "overloaded" in str(e).lower() and i < retries - 1:
                time.sleep(delay)
            else:
                return None

# Generate social content with retry
def generate_social_content_with_retry(main_content, selected_channels, retries=3, delay=5):
    generated_content = {}
    for channel in selected_channels:
        for i in range(retries):
            try:
                prompt = f"Generate a {channel.capitalize()} post based on this content:\n{main_content}\n"
                response = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}],
                )
                generated_content[channel] = response.content.strip() if response.content else ""
                break
            except Exception as e:
                if "overloaded" in str(e).lower() and i < retries - 1:
                    time.sleep(delay)
                else:
                    generated_content[channel] = ""
    return generated_content

# Get column name
def get_column_name(df, name):
    cols = [col for col in df.columns if col == name or col.startswith(name + '_')]
    return cols[0] if cols else None

# Update Google Sheet
def update_google_sheet(sheet_id, job_id, generated_content, source_row, submittee_name, selected_template):
    credentials_info = st.secrets["google_credentials"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(
        credentials_info, scopes=scopes
    )
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(sheet_id).sheet1
    target_row = source_row + 1
    timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    row_data = [selected_template, job_id, timestamp, submittee_name]
    for col, content in generated_content.items():
        row_data.append(content)
    for idx, value in enumerate(row_data, start=1):
        sheet.update_cell(target_row, idx, value)

# Main function
def main():
    st.title("Content Generator with Sheet Integration")
    source_sheet_id = "1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8"
    target_sheet_id = "1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8"
    source_data = load_google_sheet(source_sheet_id)
    examples_data = load_examples()
    if source_data.empty or examples_data.empty:
        st.error("Missing data from source sheet or examples.")
        return
    if st.button("Generate and Populate Content"):
        for idx, row in source_data.iterrows():
            job_id = row["Job ID"]
            submittee_name = row["Submittee Name"]
            selected_template = row["Selected-Template"]
            topic_description = row["Topic-Description"]
            if not all([job_id, selected_template, topic_description]):
                st.warning(f"Row {idx + 1} has missing fields.")
                continue
            template_structure = extract_template_structure(selected_template, examples_data)
            if not template_structure:
                st.warning(f"Template {selected_template} not found.")
                continue
            section_character_limits = {s[0]: s[2] for s in template_structure}
            prompt = build_template_prompt(topic_description, template_structure)
            generated_content = generate_content_with_retry(prompt, section_character_limits)
            social_content = generate_social_content_with_retry(
                " ".join(generated_content.values()), ["LinkedIn", "Facebook", "Instagram"]
            )
            generated_content.update(social_content)
            update_google_sheet(
                target_sheet_id, job_id, generated_content, idx, submittee_name, selected_template
            )
        st.success("Content generation and sheet updates complete.")

if __name__ == "__main__":
    main()
