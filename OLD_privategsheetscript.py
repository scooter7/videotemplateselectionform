import streamlit as st
import pandas as pd
import re
import anthropic
from google.oauth2.service_account import Credentials
import gspread
import time
from collections import defaultdict
import logging

# Initialize the Anthropic API client.
anthropic_api_key = st.secrets["anthropic"]["anthropic_api_key"]
client = anthropic.Anthropic(api_key=anthropic_api_key)

# Hide unwanted Streamlit elements and apply custom styles.
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

@st.cache_data
def load_examples():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    try:
        examples = pd.read_csv(url)
        return examples
    except Exception as e:
        st.error(f"Error loading examples CSV: {e}")
        return pd.DataFrame()

@st.cache_data
def load_google_sheet(sheet_id):
    """
    Loads data from a Google Sheet, automatically handling duplicate column names.
    """
    credentials_info = st.secrets["google_credentials"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    try:
        # Access the first sheet of the specified Google Sheet.
        sheet = gc.open_by_key(sheet_id).sheet1
        data = sheet.get_all_values()
        if not data:
            st.warning(f"Google Sheet with ID '{sheet_id}' is empty.")
            return pd.DataFrame()
        # Process headers and handle duplicates.
        headers = data[0]
        header_counts = defaultdict(int)
        new_headers = []
        for h in headers:
            count = header_counts[h]
            new_h = f"{h}_{count}" if count > 0 else h
            new_headers.append(new_h)
            header_counts[h] += 1
        # Create DataFrame from rows.
        rows = data[1:]
        df = pd.DataFrame(rows, columns=new_headers)
        return df
    except gspread.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An error occurred while loading the Google Sheet: {e}")
        return pd.DataFrame()

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

def extract_template_structure(selected_template, examples_data):
    """
    Extracts the structure of the specified template from the examples_data DataFrame.
    Returns a list of tuples: (section_name, text_content, max_characters).
    """
    example_row = examples_data[examples_data['Template'] == selected_template]
    if example_row.empty:
        return None
    template_structure = []
    for col in example_row.columns:
        if col != 'Template' and pd.notna(example_row[col].values[0]):
            text_element = example_row[col].values[0]
            max_chars = len(str(text_element))
            if col in ["LinkedIn", "Facebook", "Instagram"]:
                template_structure.append((col, text_element, 500))  # Default max chars.
            else:
                template_structure.append((col, text_element, max_chars))
    additional_sections = [
        ("SubmitteeName", "", 50),
        ("SelectedTemplate", selected_template, len(selected_template)),
        ("Timestamp", "", 20)
    ]
    template_structure.extend(additional_sections)
    return template_structure

def ensure_all_sections_populated(generated_content, template_structure):
    """
    Ensures all sections defined in template_structure appear in generated_content.
    """
    for section_name, text_content, _ in template_structure:
        if section_name not in generated_content:
            if section_name == "SubmitteeName":
                generated_content[section_name] = "Unknown Submittee"
            elif section_name == "SelectedTemplate":
                generated_content[section_name] = text_content
            elif section_name == "Timestamp":
                generated_content[section_name] = time.strftime("%m/%d/%Y %H:%M:%S")
            else:
                generated_content[section_name] = ""
    return generated_content

def build_template_prompt(topic_description, template_structure):
    """
    Builds a prompt for content generation based on a topic description and template structure.
    """
    if not (topic_description and template_structure):
        return None
    prompt = (
        "Using the following description, generate content for each main section as specified. "
        "Each main section should start with 'Section [Section Name]:' followed by the content. "
        "Ensure that the content for each section does not exceed the specified character limit.\n\n"
    )
    prompt += f"Description:\n{topic_description}\n\n"
    for section_name, _, max_chars in template_structure:
        if section_name == "SubmitteeName":
            prompt += f"Section {section_name}: (Provide the name of the submittee. No character limit.)\n"
        elif section_name == "SelectedTemplate":
            prompt += f"Section {section_name}: (Provide the name of the selected template. No character limit.)\n"
        elif section_name == "Timestamp":
            prompt += f"Section {section_name}: (Include the timestamp in the format mm/dd/yyyy 00:00:00. No character limit.)\n"
        else:
            prompt += f"Section {section_name}: (max {max_chars} characters)\n"
    return prompt

def generate_content_with_retry(prompt, section_character_limits, retries=3, delay=5):
    """
    Generates content via the AI model with retry logic and applies character limits.
    Returns a dictionary of sections.
    """
    for i in range(retries):
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            if isinstance(response.content, list):
                content = ''.join([block.text for block in response.content if hasattr(block, 'text')])
            else:
                content = response.content
            if not content:
                continue
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
            for section in sections:
                limit = section_character_limits.get(section, None)
                if limit and len(sections[section]) > limit:
                    trimmed_content = sections[section][:limit].rsplit(' ', 1)[0] or sections[section][:limit]
                    sections[section] = trimmed_content.strip()
            required_fields = ["SubmitteeName", "SelectedTemplate", "Timestamp"]
            for field in required_fields:
                if field not in sections:
                    if field == "Timestamp":
                        sections[field] = time.strftime("%m/%d/%Y %H:%M:%S")
                    else:
                        sections[field] = ""
            for section in section_character_limits:
                if section not in sections:
                    sections[section] = ""
            return sections
        except Exception as e:
            if 'overloaded' in str(e).lower() and i < retries - 1:
                time.sleep(delay)
            else:
                st.error(f"Error during content generation: {e}")
                return None

def generate_social_content_with_retry(main_content, selected_channels, retries=3, delay=5):
    """
    Generates social media content for the specified channels with retry logic.
    Returns a dictionary with the channel names as keys.
    """
    generated_content = {}
    for channel in selected_channels:
        for attempt in range(retries):
            try:
                prompt = f"Generate a {channel.capitalize()} post based on this content:\n{main_content}\n"
                response = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}]
                )
                if isinstance(response.content, list):
                    content = ''.join([block.text for block in response.content if hasattr(block, 'text')])
                else:
                    content = response.content
                if content:
                    generated_content[channel] = content.strip()
                else:
                    generated_content[channel] = ""
                break
            except Exception as e:
                st.error(f"Error generating content for {channel} (attempt {attempt + 1}): {e}")
                if 'overloaded' in str(e).lower() and attempt < retries - 1:
                    time.sleep(delay)
                else:
                    generated_content[channel] = ""
    return generated_content

def divide_content_verbatim(main_content, subsections, section_character_limits):
    """
    Divides the main content into subsections based on character limits.
    Returns a dictionary mapping subsection names to content.
    """
    words = main_content.split()
    total_words = len(words)
    subsections_content = {}
    start_idx = 0
    for subsection in subsections:
        limit = section_character_limits.get(subsection, None)
        if limit is None:
            subsections_content[subsection] = ""
            continue
        current_content = ''
        while start_idx < total_words:
            word = words[start_idx]
            if len(word) > limit:
                if not current_content:
                    current_content = word
                break
            if len(current_content) + len(word) + (1 if current_content else 0) > limit:
                break
            if current_content:
                current_content += ' '
            current_content += word
            start_idx += 1
        if not current_content and start_idx < total_words:
            current_content = words[start_idx]
            start_idx += 1
        subsections_content[subsection] = current_content.strip()
    if start_idx < total_words and subsections:
        last_subsection = subsections[-1]
        remaining_content = ' '.join(words[start_idx:])
        subsections_content[last_subsection] = (subsections_content.get(last_subsection, "") + ' ' + remaining_content).strip()
    return subsections_content

def get_column_name(df, name):
    """
    Finds a column in the DataFrame that matches the name or starts with the name followed by an underscore.
    Returns the column name or None if not found.
    """
    cols = [col for col in df.columns if col.lower() == name.lower() or col.lower().startswith(name.lower() + '_')]
    if not cols:
        logging.warning(f"Column '{name}' not found in DataFrame.")
    return cols[0] if cols else None

def update_google_sheet(sheet_id, job_id, generated_content, source_row, submittee_name, selected_template):
    """
    Updates the specified Google Sheet with the generated content.
    Also updates Job ID, Submittee Name, Selected Template, and Timestamp.
    """
    credentials_info = st.secrets["google_credentials"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        # Locate Job ID in Column B.
        cell = sheet.find(job_id, in_column=2)
        if not cell:
            target_row = source_row + 1
            sheet.update_cell(target_row, 2, job_id)
        else:
            target_row = cell.row
        # Update Submittee Name, Selected Template, and Timestamp.
        sheet.update_cell(target_row, 4, submittee_name)
        sheet.update_cell(target_row, 1, selected_template)
        timestamp = time.strftime("%m/%d/%Y %H:%M:%S")
        sheet.update_cell(target_row, 3, timestamp)
        # Mapping of content sections to columns.
        column_mapping = {
            'Text01': 'I', 'Text01-1': 'J', 'Text01-2': 'K', 'Text01-3': 'L', 'Text01-4': 'M',
            '01BG-Theme-Text': 'N',
            'Text02': 'O', 'Text02-1': 'P', 'Text02-2': 'Q', 'Text02-3': 'R', 'Text02-4': 'S',
            '02BG-Theme-Text': 'T',
            'Text03': 'U', 'Text03-1': 'V', 'Text03-2': 'W', 'Text03-3': 'X', 'Text03-4': 'Y',
            '03BG-Theme-Text': 'Z',
            'Text04': 'AA', 'Text04-1': 'AB', 'Text04-2': 'AC', 'Text04-3': 'AD', 'Text04-4': 'AE',
            '04BG-Theme-Text': 'AF',
            'Text05': 'AG', 'Text05-1': 'AH', 'Text05-2': 'AI', 'Text05-3': 'AJ', 'Text05-4': 'AK',
            '05BG-Theme-Text': 'AL',
            'Text06': 'AM', 'Text06-1': 'AN', 'Text06-2': 'AO', 'Text06-3': 'AP', 'Text06-4': 'AQ',
            '06BG-Theme-Text': 'AR',
            'Text07': 'AS', 'Text07-1': 'AT', 'Text07-2': 'AU', 'Text07-3': 'AV', 'Text07-4': 'AW',
            '07BG-Theme-Text': 'AX',
            'Text08': 'AY', 'Text08-1': 'AZ', 'Text08-2': 'BA', 'Text08-3': 'BB', 'Text08-4': 'BC',
            '08BG-Theme-Text': 'BD',
            'Text09': 'BE', 'Text09-1': 'BF', 'Text09-2': 'BG', 'Text09-3': 'BH', 'Text09-4': 'BI',
            '09BG-Theme-Text': 'BJ',
            'Text10': 'BK', 'Text10-1': 'BL', 'Text10-2': 'BM', 'Text10-3': 'BN', 'Text10-4': 'BO',
            '10BG-Theme-Text': 'BP',
            'CTA-Text': 'BQ', 'CTA-Text-1': 'BR', 'CTA-Text-2': 'BS', 'Tagline-Text': 'BT',
            'LinkedIn-Post-Content-Reco': 'BV',
            'Facebook-Post-Content-Reco': 'BW',
            'Instagram-Post-Content-Reco': 'BX'
        }
        for section, content in generated_content.items():
            if section in column_mapping:
                col = column_mapping[section]
                col_index = gspread.utils.a1_to_rowcol(col + str(1))[1]
                sheet.update_cell(target_row, col_index, content)
            else:
                st.warning(f"Section {section} not found in the hard-coded column mapping.")
        # Mark the row as complete in Column CC (column index 81).
        sheet.update_cell(target_row, 81, "complete")
        st.success(f"Updated Google Sheet for Job ID {job_id} in row {target_row}")
    except Exception as e:
        st.error(f"Error updating Google Sheet: {e}")

def main():
    st.title("AI Script Generator from Google Sheets and Templates")
    st.markdown("---")
    # Load input data and examples.
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
    # Load output sheet and determine the status column.
    output_sheet_id = '1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8'
    output_sheet_data = load_google_sheet(output_sheet_id)
    output_job_id_col = get_column_name(output_sheet_data, 'Job ID') if not output_sheet_data.empty else None
    status_col = output_sheet_data.columns[80] if len(output_sheet_data.columns) > 80 else None
    if 'generated_contents' not in st.session_state:
        st.session_state['generated_contents'] = []
    # When the button is pressed:
    if st.button("Generate Content"):
        generated_contents = []
        job_id_col = get_column_name(sheet_data, 'Job ID')
        selected_template_col = get_column_name(sheet_data, 'Selected-Template')
        topic_description_col = get_column_name(sheet_data, 'Topic-Description')
        submittee_name_col = get_column_name(sheet_data, 'Submittee-Name')
        if not all([job_id_col, selected_template_col, topic_description_col, submittee_name_col]):
            st.error("Required columns ('Job ID', 'Selected-Template', 'Topic-Description', 'Submittee-Name') not found.")
            return
        # Iterate over each row.
        for idx, row in sheet_data.iterrows():
            job_id_str = str(row[job_id_col]).strip()
            skip_this = False
            # Check if this row is already marked complete in the output sheet.
            if output_sheet_data is not None and output_job_id_col and status_col:
                output_sheet_data[output_job_id_col] = output_sheet_data[output_job_id_col].astype(str).str.strip()
                existing_rows = output_sheet_data[output_sheet_data[output_job_id_col] == job_id_str]
                if not existing_rows.empty:
                    for _, out_row in existing_rows.iterrows():
                        status_val = str(out_row[status_col]).strip().lower()
                        if status_val == "complete":
                            st.info(f"Row {idx + 1} with Job ID {job_id_str} is already complete. Skipping generation.")
                            skip_this = True
                            break
            if skip_this:
                continue
            selected_template = row[selected_template_col]
            topic_description = row[topic_description_col]
            submittee_name = row[submittee_name_col]
            st.write(f"Processing row {idx + 1}: Job ID = {job_id_str}, Selected Template = {selected_template}, Topic Description = {topic_description}")
            if not (job_id_str and selected_template and topic_description and submittee_name):
                st.warning(f"Row {idx + 1} is missing required data. Skipping.")
                continue
            template_structure = extract_template_structure(selected_template, examples_data)
            if template_structure is None:
                st.warning(f"Template {selected_template} not found in examples data. Skipping row {idx + 1}.")
                continue
            section_character_limits = {name: max_chars for name, _, max_chars in template_structure}
            prompt = build_template_prompt(topic_description, template_structure)
            if not prompt:
                st.warning(f"Failed to build prompt for row {idx + 1}. Skipping this row.")
                continue
            st.write(f"Generated prompt for row {idx + 1}:\n{prompt}")
            generated_content = generate_content_with_retry(prompt, section_character_limits)
            if generated_content:
                st.write(f"Content generated successfully for row {idx + 1}, Job ID = {job_id_str}")
                generated_content = ensure_all_sections_populated(generated_content, template_structure)
                full_content = generated_content.copy()
                for main_section in full_content:
                    subsections = [s for s, _, _ in template_structure if s.startswith(f"{main_section}-")]
                    if subsections:
                        main_content = generated_content[main_section]
                        subsection_character_limits = {s: section_character_limits[s] for s in subsections}
                        divided_contents = divide_content_verbatim(main_content, subsections, subsection_character_limits)
                        generated_content.update(divided_contents)
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
                generated_contents.append((job_id_str, generated_content))
                update_google_sheet(
                    output_sheet_id,
                    job_id_str,
                    generated_content,
                    idx + 1,
                    submittee_name,
                    selected_template
                )
            else:
                st.error(f"No content generated for row {idx + 1}, Job ID = {job_id_str}")
        st.session_state['generated_contents'] = generated_contents
        for job_id, content in generated_contents:
            st.subheader(f"Generated Content for Job ID: {job_id}")
            for section, text in content.items():
                st.text_area(f"Section {section}", text, height=100, key=f"text_area_{job_id}_{section}")
            st.markdown("---")
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
