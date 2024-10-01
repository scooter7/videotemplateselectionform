import streamlit as st
import pandas as pd
import re
import openai
from google.oauth2.service_account import Credentials
import gspread

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

# Display logo
st.markdown(
    """
    <div class="logo-container">
        <img src="https://mir-s3-cdn-cf.behance.net/project_modules/1400/da17b078065083.5cadb8dec2e85.png" alt="Logo">
    </div>
    """,
    unsafe_allow_html=True
)

# Set up Google Sheets API credentials using Streamlit secrets
credentials_info = st.secrets["google_credentials"]
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# Initialize Google Sheets API client with scopes
credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
gc = gspread.authorize(credentials)

# Load Google Sheet data
@st.cache_data
def load_google_sheet(sheet_name):
    sheet = gc.open(sheet_name).sheet1
    data = pd.DataFrame(sheet.get_all_records())
    return data

sheet_data = load_google_sheet('Your Sheet Name')  # Replace with your Google Sheet name

# OpenAI API key
openai.api_key = st.secrets["openai_api_key"]

client = openai

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

# Build the prompt for content generation
def build_template_prompt(sheet_row):
    job_number = sheet_row['Job Number']
    template_number = sheet_row['Template']
    description = sheet_row['Description']

    prompt = f"Create content using the following description as the main focus:\n\n'{description}'\n\n"
    prompt += f"Use the following template number for guidance: {template_number}\n"

    return prompt, job_number

# Generate content using OpenAI API
def generate_content(prompt, job_number):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    content = completion.choices[0].message.content.strip()
    content_clean = clean_text(content)
    return f"Job Number {job_number}: {content_clean}"

# Main application function
def main():
    st.title("AI Script Generator from Google Sheets")
    st.markdown("---")

    if sheet_data.empty:
        st.error("No data available from Google Sheets.")
        return

    st.dataframe(sheet_data)

    if st.button("Generate Content"):
        generated_contents = []
        for idx, row in sheet_data.iterrows():
            prompt, job_number = build_template_prompt(row)
            generated_content = generate_content(prompt, job_number)
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

    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
