import streamlit as st
import pandas as pd
import openai
import re
from st_gsheets_connection import connect_to_google_sheets

# Add custom CSS to hide the header and toolbar
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

# Add logo
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

st.markdown(
    """
    <div class="logo-container">
        <img src="https://mir-s3-cdn-cf.behance.net/project_modules/1400/da17b078065083.5cadb8dec2e85.png" alt="Logo">
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="app-container">', unsafe_allow_html=True)

# Load Streamlit secrets for API keys
openai.api_key = st.secrets["openai_api_key"]

# Create the OpenAI API client
client = openai

# Function to remove emojis and asterisks from text
def clean_text(text):
    text = re.sub(r'\*\*', '', text)  # Remove asterisks
    emoji_pattern = re.compile(
        "[" 
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text)

# Connect to Google Sheets using st-gsheets-connection
@st.cache_data
def load_google_sheet():
    gs_client = connect_to_google_sheets(st.secrets["gcp_service_account"])
    sheet_url = "https://docs.google.com/spreadsheets/d/1PcbiQInE3phuF6-YVpbZGoXs7ROz_7i2l5vaA1hZWGw/edit?usp=sharing"
    sheet = gs_client.open_by_url(sheet_url)
    worksheet = sheet.worksheet("Sheet1")  # Replace with your sheet name
    return pd.DataFrame(worksheet.get_all_records())

# Load data from Google Sheets
sheet_data = load_google_sheet()

# Function to build the OpenAI prompt based on Google Sheet data
def build_template_prompt(sheet_row):
    template_number = sheet_row['Template']
    description = sheet_row['Description']
    label = sheet_row['Label']

    prompt = f"Create content using the following description as the main focus:\n\n'{description}'\n\nUse the following structure and tone for guidance, but do not copy verbatim:\n\n"
    # You can add more structure or additional rules here if needed.

    return prompt, label

# Function to generate content using OpenAI's GPT-4o
def generate_content(prompt, label):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    content = completion.choices[0].message.content.strip()
    content_clean = clean_text(content)  # Remove asterisks and emojis
    
    return label + ": " + content_clean

# Main function with session state handling
def main():
    st.title("AI Script Generator from Google Sheets")
    st.markdown("---")

    # Check if data is loaded
    if sheet_data.empty:
        st.error("No data available from Google Sheets.")
        return

    # Display available rows in the Google Sheet
    st.dataframe(sheet_data)

    # Generate content based on Google Sheet rows
    if st.button("Generate Content from Google Sheets"):
        generated_contents = []
        for idx, row in sheet_data.iterrows():
            prompt, label = build_template_prompt(row)
            generated_content = generate_content(prompt, label)
            generated_contents.append(generated_content)
        
        full_content = "\n\n".join(generated_contents)
        st.text_area("Generated Content", full_content, height=300)

        # Add download button for the generated content
        st.download_button(
            label="Download Generated Content",
            data=full_content,
            file_name="generated_content.txt",
            mime="text/plain"
        )

    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
