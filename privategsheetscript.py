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

# Load Google Sheet data
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

# Load examples CSV file from GitHub
@st.cache_data
def load_examples():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    try:
        examples = pd.read_csv(url)
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

# Build the prompt for content generation based on the Google Sheets row and template examples
def build_template_prompt(sheet_row, examples_data):
    job_id = sheet_row['Job ID']  # Extracting job ID
    selected_template = sheet_row['Selected-Template']  # Extracting template
    topic_description = sheet_row['Topic-Description']  # Extracting topic description

    if not (job_id and selected_template and topic_description):
        return None, None

    # Extract the template number
    if "template_SH_" in selected_template:
        try:
            template_number = int(selected_template.split('_')[-1])
            template_number_str = f"{template_number:02d}"  # Ensure two digits (01, 02, ..., 06)
        except ValueError:
            template_number_str = "01"  # Fallback to default if parsing fails
    else:
        template_number_str = "01"  # Fallback to default

    # Retrieve the correct row from the examples data corresponding to the template
    example_row = examples_data[examples_data['Template'] == f'template_SH_{template_number_str}']
    
    if example_row.empty:
        st.error(f"No example found for template {selected_template}.")
        return None, None

    # Initialize the prompt for the content generation
    prompt = f"Create content using the following description:\n\n'{topic_description}'\n\n"
    
    # Add each section based on the template rules
    for col in example_row.columns[1:]:  # Skip the 'Template' column, focus on the sections
        text_element = example_row[col].values[0]
        if pd.notna(text_element):
            section_name = col  # Example: 'Text01-1'
            prompt += f"{section_name}: {text_element}\n"

    return prompt, job_id

# Generate content using OpenAI API
def generate_content(prompt, job_id):
    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        content = completion.choices[0].message.content.strip()
        content_clean = clean_text(content)
        return f"Job ID {job_id}: {content_clean}"
    except Exception as e:
        st.error(f"Error generating content: {e}")
        return None

# Generate social media content
def generate_social_content(main_content, selected_channels):
    social_prompts = {
        "facebook": f"Generate a Facebook post based on this content:\n{main_content}",
        "linkedin": f"Generate a LinkedIn post based on this content:\n{main_content}",
        "instagram": f"Generate an Instagram post based on this content:\n{main_content}"
    }
    generated_content = {}
    for channel in selected_channels:
        try:
            prompt = social_prompts[channel]
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            generated_content[channel] = clean_text(completion.choices[0].message.content.strip())
        except Exception as e:
            st.error(f"Error generating {channel} content: {e}")
    return generated_content

# Main application function
def main():
    st.title("AI Script Generator from Google Sheets and Templates")
    st.markdown("---")

    # Load the data from Google Sheets and the examples CSV
    sheet_data = load_google_sheet('1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8')
    examples_data = load_examples()

    if sheet_data.empty or examples_data.empty:
        st.error("No data available from Google Sheets or Templates CSV.")
        return

    st.dataframe(sheet_data)

    if st.button("Generate Content"):
        generated_contents = []
        for idx, row in sheet_data.iterrows():
            prompt, job_id = build_template_prompt(row, examples_data)

            if not prompt or not job_id:
                continue

            generated_content = generate_content(prompt, job_id)
            if generated_content:
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

    if selected_channels and 'full_content' in st.session_state:
        if st.button("Generate Social Media Content"):
            social_content = generate_social_content(st.session_state['full_content'], selected_channels)
            st.session_state['social_content'] = social_content

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
