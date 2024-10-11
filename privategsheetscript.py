import streamlit as st
import re
import anthropic
from google.oauth2.service_account import Credentials
import gspread
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

# Function to load the Google Sheet
def load_google_sheet(sheet_id):
    credentials_info = st.secrets["google_credentials"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        data = sheet.get_all_records()

        return data
    except gspread.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found.")
        return []
    except Exception as e:
        st.error(f"An error occurred while loading the Google Sheet: {e}")
        return []

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
            return f"Job ID {job_id}:\n\n{content_clean}"
        
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

        # Find the row that matches the Job ID
        for i, row in enumerate(rows):
            if row[1].strip().lower() == job_id.strip().lower():  # Assuming Job ID is in column B
                row_index = i + 1  # Sheet rows are 1-indexed

                # Update the relevant columns (H-BS for text content)
                for idx, content in enumerate(generated_content):
                    column_letter = chr(72 + idx)  # Columns H to BS for text content
                    sheet.update_acell(f'{column_letter}{row_index}', content)
                    time.sleep(1)  # Add a delay to avoid rate limits

                # Update the social media columns (BU-BZ for social media content)
                social_media_columns = ["BU", "BV", "BW", "BX", "BY", "BZ"]  # Adjust based on exact columns in your sheet
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

    if not sheet_data:
        st.error("No data available from the Google Sheet.")
        return

    st.write("Sheet Data:", sheet_data)

    # Ensure session state management for content generation
    if 'generated_contents' not in st.session_state:
        st.session_state['generated_contents'] = []

    if st.button("Generate Content"):
        generated_contents = []
        for idx, row in enumerate(sheet_data):
            if not (row['Job ID'] and row['Selected-Template'] and row['Topic-Description']):
                st.warning(f"Row {idx + 1} is missing Job ID, Selected-Template, or Topic-Description. Skipping this row.")
                continue

            # Assuming a valid template structure was built previously
            prompt, job_id = "Your template prompt here", row['Job ID']  # Simulate your build_template_prompt function

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
                # Generate social content based on the specific row's generated content
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
    
    # Input for Google Sheet ID (for the second sheet where content is populated)
    sheet_id = st.text_input("Enter the target Google Sheet ID", "1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8")
    
    if st.button("Update Google Sheet"):
        for idx, generated_content in enumerate(st.session_state['generated_contents']):
            job_id = sheet_data[idx]['Job ID']
            social_media_content = st.session_state['social_media_contents'][idx] if 'social_media_contents' in st.session_state else {}

            # Update Google Sheet
            update_google_sheet_with_generated_content(sheet_id, job_id, generated_content, social_media_content)

    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
