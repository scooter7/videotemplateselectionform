import streamlit as st
import pandas as pd
import re
import openai
from google.oauth2.service_account import Credentials
import gspread

# Access OpenAI API key from [openai] in secrets.toml
openai.api_key = st.secrets["openai"]["openai_api_key"]

client = openai

# Hide Streamlit branding
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

# Custom CSS for the UI elements
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

# Set up Google Sheets API credentials using Streamlit secrets
credentials_info = st.secrets["google_credentials"]
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# Initialize Google Sheets API client with scopes
credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
gc = gspread.authorize(credentials)

# Load Google Sheet data using ID
@st.cache_data
def load_google_sheet(sheet_id):
    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        data = pd.DataFrame(sheet.get_all_records())
        return data
    except gspread.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found. Please check the ID and sharing permissions.")
        return pd.DataFrame()  # Return an empty dataframe

# Load examples CSV file from GitHub with debug info
@st.cache_data
def load_examples():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    try:
        examples = pd.read_csv(url)
        st.write("Examples CSV loaded successfully.")
        st.dataframe(examples)  # Display the loaded examples for debugging
        st.write("Column names in the examples CSV:", examples.columns.tolist())  # Debug: Print column names
        return examples
    except Exception as e:
        st.error(f"Error loading examples CSV: {e}")
        return pd.DataFrame()

# Text cleaning function
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

# Build the prompt for content generation based on updated columns and template examples
def build_template_prompt(sheet_row, examples_data):
    job_id = sheet_row['Job ID']  # Now from column C
    selected_template = sheet_row['Selected-Template']  # Now from column G
    topic_description = sheet_row['Topic-Description']  # Now from column H

    # Check if all required fields are non-empty
    if not (job_id and selected_template and topic_description):
        return None, None

    # Check if the selected_template follows the expected format
    if "template_SH_" in selected_template:
        # Extract template number from template_SH_XX and format it to two digits
        try:
            template_number = int(selected_template.split('_')[-1])
            template_number_str = f"{template_number:02d}"  # Ensure two digits
        except ValueError:
            st.error(f"Invalid template format for Job ID {job_id}. Using default template.")
            template_number_str = "01"  # Default template number in case of failure
    else:
        st.error(f"Invalid template format for Job ID {job_id}. Using default template.")
        template_number_str = "01"  # Default template number in case of invalid format

    # Find the matching template row in the CSV
    example_row = examples_data[examples_data['Template'] == f'template_SH_{template_number_str}']

    if example_row.empty:
        st.error(f"No example found for template {selected_template}.")
        return None, None

    # Dynamically build the prompt using the template structure and the content from the Google Sheet
    prompt = f"{job_id}\n"
    for col in example_row.columns[1:]:
        template_text = example_row[col].values[0]  # From the CSV
        google_sheet_text = sheet_row.get(col, '')  # From the Google Sheet content
        
        # If the column exists in both the template and the sheet, insert content
        if pd.notna(template_text) and google_sheet_text:
            prompt += f"{col}: {google_sheet_text}\n"  # Insert content into the appropriate sections

    return prompt, job_id

# Generate content using OpenAI API
def generate_content(prompt, job_id):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    content = completion.choices[0].message.content.strip()
    content_clean = clean_text(content)
    return content_clean  # No commentary, only the generated copy

# Generate social media content based on the main content
def generate_social_content(main_content, selected_channels):
    social_prompts = {
        "facebook": f"Generate a Facebook post based on the following content:\n{main_content}\nUse a tone similar to the posts on https://www.facebook.com/ShiveHattery.",
        "linkedin": f"Generate a LinkedIn post based on the following content:\n{main_content}\nUse a tone similar to the posts on https://www.linkedin.com/company/shive-hattery/.",
        "instagram": f"Generate an Instagram post based on the following content:\n{main_content}\nUse a tone similar to the posts on https://www.instagram.com/shivehattery/."
    }
    generated_content = {}
    for channel in selected_channels:
        prompt = social_prompts[channel]
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        generated_content[channel] = clean_text(completion.choices[0].message.content.strip())
    return generated_content

# Main application function
def main():
    st.title("AI Script Generator from Google Sheets")
    st.markdown("---")

    # Load data
    sheet_data = load_google_sheet('1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8')
    examples_data = load_examples()

    if sheet_data.empty:
        st.error("No data available from Google Sheets.")
        return

    st.dataframe(sheet_data)

    if st.button("Generate Content"):
        generated_contents = []
        for idx, row in sheet_data.iterrows():
            prompt, job_id = build_template_prompt(row, examples_data)

            # Skip rows where prompt or job_id is None (i.e., when required fields are missing)
            if not prompt or not job_id:
                continue

            generated_content = generate_content(prompt, job_id)
            generated_contents.append(generated_content)

        full_content = "\n\n".join(generated_contents)
        st.session_state['full_content'] = full_content
        st.text_area("Generated Content", full_content, height=300)

        st.download_button(
            label="Download Generated Content",
            data=full_content,
            file_name="generated_content.txt",
            mime="text/plain"
        )

    st.markdown("---")
    st.header("Generate Social Media Posts")
    facebook = st.checkbox("Facebook")
    linkedin = st.checkbox("LinkedIn")
    instagram = st.checkbox("Instagram")

    selected_channels = []
    if facebook:
        selected_channels.append("facebook")
    if linkedin:
        selected_channels.append("linkedin")
    if instagram:
        selected_channels.append("instagram")

    # Ensure full_content exists before generating social media posts
    if selected_channels and 'full_content' in st.session_state:
        if st.button("Generate Social Media Content"):
            st.session_state['social_content'] = generate_social_content(st.session_state['full_content'], selected_channels)

    if 'social_content' in st.session_state:
        for channel, content in st.session_state['social_content'].items():
            st.subheader(f"{channel.capitalize()} Post")
            st.text_area(f"{channel.capitalize()} Content", content, height=200)
            st.download_button(
                label=f"Download {channel.capitalize()} Content",
                data=content,
                file_name=f"{channel}_post.txt",
                mime="text/plain"
            )

    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
