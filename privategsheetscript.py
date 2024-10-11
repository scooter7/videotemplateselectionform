import streamlit as st
import re
import anthropic
from google.oauth2.service_account import Credentials
import gspread
import pandas as pd
import time

# Initialize the Anthropic client
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

# Load Google Sheet data
def load_google_sheet(sheet_id):
    credentials_info = st.secrets["google_credentials"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except gspread.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An error occurred while loading the Google Sheet: {e}")
        return pd.DataFrame()

# Extract the template structure from examples
def extract_template_structure(selected_template, examples_data):
    # Debugging: Remove the print statement now that we know the correct column name
    # st.write("Columns in examples_data:", examples_data.columns)
    
    if "template_SH_" in selected_template:
        try:
            template_number = int(selected_template.split('_')[-1])
            template_number_str = f"{template_number:02d}"
        except ValueError:
            template_number_str = "01"
    else:
        template_number_str = "01"

    # Use 'Selected-Template' instead of 'Template'
    example_row = examples_data[examples_data['Selected-Template'] == f'template_SH_{template_number_str}']
    
    if example_row.empty:
        return None

    template_structure = []
    for col in possible_columns:
        if col in example_row.columns:
            text_element = example_row[col].values[0]
            if pd.notna(text_element):
                template_structure.append((col, text_element))

    return template_structure

# Build template-based prompt for content generation
def build_template_prompt(sheet_row, template_structure):
    job_id = sheet_row['Job ID']  # Accessing 'Job ID' from the requests sheet
    topic_description = sheet_row['Topic-Description']  # Ensure matching column name with the requests sheet

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

# Clean text by removing unnecessary characters
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

# Retry generating content with API
def generate_content_with_retry(prompt, job_id, retries=3, delay=5):
    for i in range(retries):
        try:
            # Attempt to generate content with the API
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
            return f"Job ID {job_id}:\n\n{content_clean}"
        
        except anthropic.APIError as e:
            # Log the error message and retry after a delay
            st.warning(f"API Error occurred: {str(e)}. Retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
            time.sleep(delay)
        except Exception as e:
            # Handle any other exception and log it
            st.error(f"An unexpected error occurred: {str(e)}")
            break  # Stop retrying if any other exception occurs

    return None  # Return None if all retries fail

# Generate social media content with retry
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
                break  # Break the retry loop if successful
            
            except anthropic.APIError as e:
                if e.error.get('type') == 'overloaded_error' and i < retries - 1:
                    st.warning(f"API is overloaded for {channel}, retrying in {delay} seconds... (Attempt {i + 1} of {retries})")
                    time.sleep(delay)
                else:
                    st.error(f"Error generating {channel} content: {e}")
    return generated_content

# Function to update Google Sheet with generated content directly via row index
def update_google_sheet_with_generated_content(sheet_id, job_id, generated_content, social_media_content):
    credentials_info = st.secrets["google_credentials"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    
    try:
        # Open the target sheet (this is now the second sheet to populate)
        sheet = gc.open_by_key(sheet_id).sheet1
        rows = sheet.get_all_values()

        # Find the row that matches the Job ID in the target sheet ('Job-ID')
        for i, row in enumerate(rows):
            if row[1].strip().lower() == job_id.strip().lower():  # Assuming Job-ID is in column B
                row_index = i + 1  # Sheet rows are 1-indexed

                # Update the relevant columns (H-BS for text content)
                for idx, content in enumerate(generated_content):
                    column_letter = chr(72 + idx)  # Columns H to BS for text content
                    sheet.update_acell(f'{column_letter}{row_index}', content)
                    time.sleep(1)  # Add a delay to avoid rate limits

                # Update the social media columns (BU-BZ for social media content)
                social_media_columns = ["BU", "BV", "BW", "BX", "BY", "BZ"]
                for idx, (channel, social_content) in enumerate(social_media_content.items()):
                    column_letter = social_media_columns[idx]
                    sheet.update_acell(f'{column_letter}{row_index}', social_content)
                    time.sleep(1)  # Add a delay to avoid rate limits

                st.success(f"Content for Job ID {job_id} successfully updated in the Google Sheet.")
                return

        st.error(f"No matching Job ID found for '{job_id}' in the target sheet.")

    except gspread.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found.")
    except Exception as e:
        st.error(f"An error occurred while updating the Google Sheet: {e}")

def main():
    st.title("AI Script Generator from Google Sheets and Templates")
    st.markdown("---")

    # Load data only if not already stored in session_state
    if 'sheet_data' not in st.session_state:
        st.session_state['sheet_data'] = load_google_sheet('1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8')

    sheet_data = st.session_state['sheet_data']

    # Fix: Correctly checking if the DataFrame is empty
    if sheet_data.empty:
        st.error("No data available from the Google Sheet.")
        return

    st.write("Sheet Data:", sheet_data)

    # Ensure session state management for content generation
    if 'generated_contents' not in st.session_state:
        st.session_state['generated_contents'] = []

    if st.button("Generate Content"):
        generated_contents = []
        for idx, row in sheet_data.iterrows():
            if not (row['Job ID'] and row['Selected-Template'] and row['Topic-Description']):  # Use 'Job ID' from the requests sheet
                st.warning(f"Row {idx + 1} is missing Job ID, Selected-Template, or Topic-Description. Skipping this row.")
                continue

            template_structure = extract_template_structure(row['Selected-Template'], sheet_data)
            if template_structure is None:
                continue

            prompt, job_id = build_template_prompt(row, template_structure)

            generated_content = generate_content_with_retry(prompt, job_id)
            if generated_content:
                generated_contents.append(generated_content)

        st.session_state['generated_contents'] = generated_contents
        full_content = "\n\n".join(generated_contents)
        st.text_area("Generated Content", full_content, height=300)

        st.download_button(
            label="Download Generated Content",
            data=full_content,
            file_name="generated_content.txt",
            mime="text/plain"
        )

    st.markdown("---")
    st.header("Generate Social Media Posts")
    
    # Checkbox management with session state
    if 'selected_channels' not in st.session_state:
        st.session_state['selected_channels'] = []

    facebook = st.checkbox("Facebook", value="facebook" in st.session_state['selected_channels'])
    linkedin = st.checkbox("LinkedIn", value="linkedin" in st.session_state['selected_channels'])
    instagram = st.checkbox("Instagram", value="instagram" in st.session_state['selected_channels'])

    # Update session state based on checkbox selection
    selected_channels = []
    if facebook:
        selected_channels.append("facebook")
    if linkedin:
        selected_channels.append("linkedin")
    if instagram:
        selected_channels.append("instagram")
    
    st.session_state['selected_channels'] = selected_channels

    if selected_channels and 'generated_contents' in st.session_state:
        # Ensure session state management for social content
        if 'social_media_contents' not in st.session_state:
            st.session_state['social_media_contents'] = []

        if st.button("Generate Social Media Content"):
            social_media_contents = []
            for idx, generated_content in enumerate(st.session_state['generated_contents']):
                social_content_for_row = generate_social_content_with_retry(generated_content, selected_channels)
                if social_content_for_row:
                    social_media_contents.append(social_content_for_row)
            
            st.session_state['social_media_contents'] = social_media_contents

    # Display the social media content for each channel and row
    if 'social_media_contents' in st.session_state:
        for idx, social_content in enumerate(st.session_state['social_media_contents']):
            st.subheader(f"Generated Social Media Content for Row {idx + 1}")
            for channel, content in social_content.items():
                st.subheader(f"{channel.capitalize()} Post")
                st.text_area(f"{channel.capitalize()} Content", content, height=200, key=f"{channel}_content_{idx}")
                st.download_button(
                    label=f"Download {channel.capitalize()} Content",
                    data=content,
                    file_name=f"{channel}_post_row{idx + 1}.txt",
                    mime="text/plain",
                    key=f"download_{channel}_row_{idx}"
                )

    # New section: Update Google Sheet
    st.markdown("---")
    st.header("Update Google Sheet with Generated Content")
    
    # Input for Google Sheet ID
    sheet_id = st.text_input("Enter the target Google Sheet ID", "1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8")
    
    if st.button("Update Google Sheet"):
        for idx, generated_content in enumerate(st.session_state['generated_contents']):
            job_id = sheet_data.loc[idx, 'Job ID']  # From the requests sheet
            social_media_content = st.session_state['social_media_contents'][idx] if 'social_media_contents' in st.session_state else {}

            update_google_sheet_with_generated_content(sheet_id, job_id, generated_content, social_media_content)

    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
