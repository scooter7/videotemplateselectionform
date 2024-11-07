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
                max_chars = len(str(text_element))
                template_structure.append((col, text_element, max_chars))
    return template_structure

def ensure_all_sections_populated(generated_content, template_structure):
    """
    Ensure that all required sections based on the template are populated, even if they are empty.
    """
    for section_name, _, _ in template_structure:
        if section_name not in generated_content:
            generated_content[section_name] = ""  # Ensure all sections are populated, even if empty
    return generated_content

def build_template_prompt(topic_description, template_structure):
    if not (topic_description and template_structure):
        return None

    prompt = f"{anthropic.HUMAN_PROMPT}Using the following description, generate content for each main section as specified. Each main section should start with 'Section [Section Name]:' followed by the content. Do not generate content for subsections. Ensure that the content for each section does not exceed the specified character limit. Do not include any mention of character counts or limits in your output.\n\n"
    prompt += f"Description:\n{topic_description}\n\n"

    for section_name, _, max_chars in template_structure:
        if '-' not in section_name:
            prompt += f"Section {section_name}: (max {max_chars} characters)\n"

    prompt += "\nPlease provide the content for each main section as specified, starting each with 'Section [Section Name]:'. Do not include subsections. Do not include any additional text or explanations.\n" + anthropic.AI_PROMPT

    return prompt

def generate_content_with_retry(prompt, section_character_limits, retries=3, delay=5):
    for i in range(retries):
        try:
            response = client.completions.create(
                prompt=prompt,
                model="claude-2",
                max_tokens_to_sample=2000,
                temperature=0.1,  # Changed temperature to 0.1
            )

            content = response.completion if response.completion else "No content generated."

            content_clean = clean_text(content)

            sections = {}
            current_section = None
            for line in content_clean.split('\n'):
                line = line.strip()
                if line.startswith("Section "):
                    section_header = line.split(":", 1)
                    if len(section_header) == 2:
                        section_name = section_header[0].replace("Section ", "").strip()
                        section_content = section_header[1].strip()
                    else:
                        section_name = line.replace("Section ", "").strip()
                        section_content = ""
                    current_section = section_name
                    sections[current_section] = section_content
                elif current_section:
                    sections[current_section] += ' ' + line.strip()

            # Trim content to character limits without cutting off mid-word
            for section in sections:
                limit = section_character_limits.get(section, None)
                if limit:
                    content = sections[section]
                    if len(content) > limit:
                        # Trim without cutting off mid-word
                        trimmed_content = content[:limit].rsplit(' ', 1)[0]
                        if not trimmed_content:
                            # If trimming removes all content, keep the original up to limit
                            trimmed_content = content[:limit]
                        sections[section] = trimmed_content.strip()
                else:
                    sections[section] = sections[section].strip()

            return sections

        except anthropic.ApiException as e:
            if 'overloaded' in str(e).lower() and i < retries - 1:
                st.warning(f"API is overloaded, retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
                time.sleep(delay)
            else:
                st.error(f"Error generating content: {e}")
                return None

def divide_content_verbatim(main_content, subsections, section_character_limits):
    words = main_content.split()
    total_words = len(words)
    num_subsections = len(subsections)
    subsections_content = {}
    start_idx = 0

    for subsection in subsections:
        limit = section_character_limits.get(subsection, None)
        if limit is None:
            continue

        current_content = ''
        while start_idx < total_words:
            word = words[start_idx]
            if len(current_content) + len(word) + (1 if current_content else 0) > limit:
                break
            if current_content:
                current_content += ' '
            current_content += word
            start_idx += 1

        # If no words could be added due to limit, add at least one word
        if not current_content and start_idx < total_words:
            current_content = words[start_idx]
            start_idx += 1

        subsections_content[subsection] = current_content.strip()

    # If there are remaining words, add them to the last subsection
    if start_idx < total_words and subsections:
        last_subsection = subsections[-1]
        remaining_content = ' '.join(words[start_idx:])
        subsections_content[last_subsection] += ' ' + remaining_content

    return subsections_content

def get_column_name(df, name):
    """
    Finds a column name in the dataframe that either matches exactly
    or starts with the specified name (useful for columns like 'Job ID').
    """
    cols = [col for col in df.columns if col == name or col.startswith(name + '_')]
    if cols:
        return cols[0]
    else:
        return None

def update_google_sheet(sheet_id, job_id, generated_content, source_row):
    """
    Updates the Google Sheet with the generated content.
    If the Job ID is not found, it creates a new row and populates it.
    Ensures that Job ID is placed in the correct row based on the source_row.
    """
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

        # Check if the job_id already exists
        cell = sheet.find(job_id, in_column=2)  # Assuming Job ID is in column B (index 2)

        if not cell:
            # Job ID not found, place it in the correct row based on the source_row
            st.warning(f"Job ID {job_id} not found. Placing it in the correct row based on source.")
            target_row = source_row + 1  # Match the row from the source Google Sheet
            sheet.update_cell(target_row, 2, job_id)  # Add Job ID in column B
        else:
            # If found, update the existing row
            target_row = cell.row

        # Retrieve headers to map sections to columns
        headers = sheet.row_values(1)
        header_to_col = {}
        header_counts = defaultdict(int)
        for idx, h in enumerate(headers):
            count = header_counts[h]
            if count > 0:
                new_h = f"{h}_{count}"
            else:
                new_h = h
            header_counts[h] += 1
            header_to_col[new_h] = idx + 1  # 1-based indexing

        # Update or insert the content for each section
        for section, content in generated_content.items():
            if section in header_to_col:
                col = header_to_col[section]
                sheet.update_cell(target_row, col, content)
            else:
                st.warning(f"Section {section} not found in sheet headers.")

        st.success(f"Updated Google Sheet for Job ID {job_id} in row {target_row}")

    except Exception as e:
        st.error(f"Error updating Google Sheet: {e}")
        
def generate_social_content_with_retry(main_content, selected_channels, retries=3, delay=5):
    """
    Generate content for social media channels with retry logic in case of API overload.
    """
    generated_content = {}
    for channel in selected_channels:
        for i in range(retries):
            try:
                prompt = f"{anthropic.HUMAN_PROMPT}Generate a {channel.capitalize()} post based on this content:\n{main_content}\n\n{anthropic.AI_PROMPT}"
                response = client.completions.create(
                    prompt=prompt,
                    model="claude-2",
                    max_tokens_to_sample=500,
                    temperature=0.1,  # Changed temperature to 0.1
                )

                content = response.completion if response.completion else "No content generated."
                generated_content[channel] = content.strip()
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

        # Iterate through all rows in the sheet
        for idx, row in sheet_data.iterrows():
            job_id = row[job_id_col]
            selected_template = row[selected_template_col]
            topic_description = row[topic_description_col]

            st.write(f"Processing row {idx + 1}: Job ID = {job_id}, Selected Template = {selected_template}, Topic Description = {topic_description}")

            if not (job_id and selected_template and topic_description):
                st.warning(f"Row {idx + 1} is missing Job ID, Selected-Template, or Topic-Description. Skipping this row.")
                continue

            # Extract template structure
            template_structure = extract_template_structure(selected_template, examples_data)
            if template_structure is None:
                st.warning(f"Template {selected_template} not found in examples data. Skipping row {idx + 1}.")
                continue

            # Build a mapping of section names to character limits
            section_character_limits = {name: max_chars for name, _, max_chars in template_structure}

            # Build prompt and generate content
            prompt = build_template_prompt(topic_description, template_structure)
            if not prompt:
                st.warning(f"Failed to build prompt for row {idx + 1}. Skipping this row.")
                continue

            st.write(f"Generated prompt for row {idx + 1}:
{prompt}")

            generated_content = generate_content_with_retry(prompt, section_character_limits)
            if generated_content:
                st.write(f"Content generated successfully for row {idx + 1}, Job ID = {job_id}")

                # Ensure all required sections are populated
                generated_content = ensure_all_sections_populated(generated_content, template_structure)

                # Divide content for subsections if needed
                full_content = generated_content.copy()
                for main_section in full_content:
                    subsections = [s for s, _, _ in template_structure if s.startswith(f"{main_section}-")]
                    if subsections:
                        main_content = generated_content[main_section]
                        subsection_character_limits = {s: section_character_limits[s] for s in subsections}
                        divided_contents = divide_content_verbatim(main_content, subsections, subsection_character_limits)
                        generated_content.update(divided_contents)

                # Generate social media content
                social_channels = ['LinkedIn', 'Facebook', 'Instagram']
                combined_content = "\n".join([f"{section}: {content}" for section, content in generated_content.items()])
                social_media_contents = generate_social_content_with_retry(combined_content, social_channels)

                social_media_section_names = {
                    'LinkedIn': 'LinkedIn-Post-Content-Reco',
                    'Facebook': 'Facebook-Post-Content-Reco',
                    'Instagram': 'Instagram-Post-Content-Reco'
                }
                for channel in social_channels:
                    section_name = social_media_section_names[channel]
                    generated_content[section_name] = social_media_contents.get(channel, "")

                generated_contents.append((job_id, generated_content))

                # Update the response sheet with generated content
                update_google_sheet('1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8', job_id, generated_content, idx + 1)
            else:
                st.error(f"No content generated for row {idx + 1}, Job ID = {job_id}")

        st.session_state['generated_contents'] = generated_contents

        for job_id, content in generated_contents:
            st.subheader(f"Generated Content for Job ID: {job_id}")
            for section, text in content.items():
                st.text_area(f"Section {section}", text, height=100, key=f"text_area_{job_id}_{section}")
            st.markdown("---")

    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
