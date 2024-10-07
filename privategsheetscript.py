import streamlit as st
import pandas as pd
import re
import anthropic
from google.oauth2.service_account import Credentials
import gspread

# Initialize Anthropics API key from Streamlit secrets
anthropic_api_key = st.secrets["anthropic"]["anthropic_api_key"]

# Initialize the Anthropic client
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
    "Text06", "Text06-1", "Text06-2", "Text06-3", "Text06-4", "06BG-Theme-Text",
    "Text07", "Text07-1", "Text07-2", "Text07-3", "Text07-4", "07BG-Theme-Text",
    "Text08", "Text08-1", "Text08-2", "Text08-3", "Text08-4", "08BG-Theme-Text",
    "Text09", "Text09-1", "Text09-2", "Text09-3", "Text09-4", "09BG-Theme-Text",
    "Text10", "Text10-1", "Text10-2", "Text10-3", "Text10-4", "10BG-Theme-Text",
    "CTA-Text", "CTA-Text-1", "CTA-Text-2", "Tagline-Text"
]

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
    for col in possible_columns:
        if col in example_row.columns:
            text_element = example_row[col].values[0]
            if pd.notna(text_element):
                template_structure.append((col, text_element))

    return template_structure

def build_template_prompt(sheet_row, template_structure):
    job_id = sheet_row['Job ID']
    topic_description = sheet_row['Topic-Description']

    if not (job_id and topic_description and template_structure):
        return None, None

    prompt = f"Create content for Job ID {job_id}.\n\nUse the following description from the Google Sheet:\n\n{topic_description}\n\n"

    prompt += "Follow this structure, but do NOT use the CSV content verbatim. Instead, generate content based on the description, keeping each section within the specified character limits:\n\n"
    
    for section_name, content in template_structure:
        max_chars = len(content)
        prompt += f"Section {section_name}: Generate content based on the description. Limit to {max_chars} characters.\n"

    return prompt, job_id

def enforce_character_limit(content, max_chars):
    if len(content) > max_chars:
        return content[:max_chars].rstrip() + "..."
    return content

def generate_content(prompt, job_id, template_structure, sheet_row):
    try:
        # Build the detailed prompt for the LLM
        structured_prompt = f"Create content for Job ID {job_id}. Follow the structure from the template but generate content only based on the Google Sheet description. Do NOT use the CSV content. Keep each section within the character limits specified."
        structured_prompt += "\n\nHere are the sections and character limits:\n"

        for section_name, max_chars in template_structure:
            structured_prompt += f"Section {section_name}: Please generate content for this section. Limit: {max_chars} characters.\n"
        
        structured_prompt += f"\n\nGoogle Sheet description for this job: {sheet_row['Topic-Description']}"

        # Make the API request
        message = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1000,  # Adjusted for token sampling
            temperature=0.7,
            messages=[
                {"role": "user", "content": structured_prompt}
            ]
        )

        # Access the content of the message
        if message and message.content:
            content = message.content[0].text.strip()

            # Enforce character limits manually if the LLM doesn't respect them
            structured_content = []
            for section_name, max_chars in template_structure:
                section_content = f"Section {section_name}: {content}"
                truncated_content = enforce_character_limit(section_content, max_chars)
                structured_content.append(truncated_content)

            final_output = "\n\n".join(structured_content)
            return f"Job ID {job_id}:\n\n{final_output}"
        else:
            st.error("No content found in the response.")
            return None
        
    except Exception as e:
        st.error(f"Error generating content: {e}")
        return None
        
    except Exception as e:
        st.error(f"Error generating content: {e}")
        return None

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
            message = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=500,  # Adjust token limit as needed
                temperature=0.7,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )

            # Access the content of the first message
            if message and message.content:
                generated_content[channel] = clean_text(message.content[0].text.strip())
            else:
                st.error(f"No content found for {channel}.")
        except Exception as e:
            st.error(f"Error generating {channel} content: {e}")
    return generated_content

def main():
    st.title("AI Script Generator from Google Sheets and Templates")
    st.markdown("---")

    sheet_data = load_google_sheet('1hUX9HPZjbnyrWMc92IytOt4ofYitHRMLSjQyiBpnMK8')
    examples_data = load_examples()

    if sheet_data.empty or examples_data.empty:
        st.error("No data available from Google Sheets or Templates CSV.")
        return

    st.dataframe(sheet_data)

    if st.button("Generate Content"):
        generated_contents = []
        for idx, row in sheet_data.iterrows():
            if not (row['Job ID'] and row['Selected-Template'] and row['Topic-Description']):
                st.warning(f"Row {idx + 1} is missing Job ID, Selected-Template, or Topic-Description. Skipping this row.")
                continue

            # Extract the template structure based on the selected template
            template_structure = extract_template_structure(row['Selected-Template'], examples_data)
            if template_structure is None:
                st.warning(f"Template structure not found for row {idx + 1}. Skipping.")
                continue

            # Build the prompt
            prompt, job_id = build_template_prompt(row, template_structure)

            if not prompt or not job_id:
                continue

            # Call the generate_content function with the required arguments
            generated_content = generate_content(prompt, job_id, template_structure, row)
            if generated_content:
                generated_contents.append(generated_content)

        # Combine the generated contents and display the result
        full_content = "\n\n".join(generated_contents)
        st.session_state['full_content'] = full_content
        st.text_area("Generated Content", full_content, height=300)

        # Provide a download button
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
