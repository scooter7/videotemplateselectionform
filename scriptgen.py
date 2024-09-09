import streamlit as st
import pandas as pd
import openai
import re
import requests

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

# Function to remove emojis from text
def remove_emojis(text):
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

# Load the CSV data from GitHub (Templates CSV)
@st.cache_data
def load_template_data():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    try:
        df = pd.read_csv(url)
        st.write("CSV Data Loaded Successfully")
        st.write("Template column values (for debugging):", df['Template'].unique())  # Show unique template names
        return df
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()  # Return empty dataframe if failed

template_data = load_template_data()

# Function to extract text elements from the template CSV and build the OpenAI prompt
def build_template_prompt(template_number, description, template_data):
    # Normalize template names by stripping whitespace and converting to lowercase
    template_data['Template'] = template_data['Template'].str.strip().str.lower()
    
    # Filter the template data for the selected template
    template_filter = f"template {template_number}".lower()
    template_row = template_data[template_data['Template'] == template_filter]

    if template_row.empty:
        return f"No data found for Template {template_number}"

    # Build the prompt based on text elements from columns C-BN
    prompt = f"Create content based on the following description:\n\n{description}\n\n"
    prompt += "Use the following structure and style for each text element:\n\n"
    
    # Iterate through the columns C-BN for the selected row to construct the prompt
    for col in template_row.columns[2:]:  # Columns C-BN
        text_element = template_row[col].values[0]  # Extract the first (and only) value for this column
        if pd.notna(text_element):  # Ensure the column is not empty
            prompt += f"{col}: {text_element}\n"
    
    prompt += "\nEnsure the content matches the character limits and style for each element."
    
    st.write(f"Generated prompt for OpenAI:\n{prompt}")  # Debug: Show the prompt

    return prompt

# Function to generate content using OpenAI's GPT-4o-mini
def generate_content(description, template_number, template_data):
    # Build the prompt based on the template and description
    prompt = build_template_prompt(template_number, description, template_data)

    # Call OpenAI API to generate content based on the constructed prompt
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    
    content = completion.choices[0].message.content.strip()
    content_no_emojis = remove_emojis(content)

    return content_no_emojis

def main():
    st.title("AI Script Generator")
    st.markdown("---")

    # Show a radio button for selecting the template (Templates 1-6)
    template_number = st.radio("Select Template", [1, 2, 3, 4, 5, 6])

    # Add a field for entering a description
    description = st.text_area("Enter a description:")

    # Generate content when the button is clicked
    if st.button("Generate Content"):
        if description and template_number:
            generated_content = generate_content(description, template_number, template_data)
            st.text_area("Generated Content", generated_content, height=300)

            # Download the generated content
            st.download_button(
                label="Download as Text",
                data=generated_content,
                file_name=f"Template_{template_number}_Content.txt",
                mime="text/plain"
            )
        else:
            st.error("Please select a template and enter a description.")

    st.markdown("---")
    st.header("Revision Section")

    with st.expander("Revision Fields"):
        pasted_content = st.text_area("Paste Generated Content Here (for further revisions):")
        revision_requests = st.text_area("Specify Revisions Here:")

    if st.button("Revise Further"):
        revision_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": pasted_content},
            {"role": "user", "content": revision_requests}
        ]
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=revision_messages
        )
        revised_content = completion.choices[0].message.content.strip()
        revised_content_no_emojis = remove_emojis(revised_content)
        st.text(revised_content_no_emojis)
        st.download_button("Download Revised Content", revised_content_no_emojis, "revised_content_revision.txt", key="download_revised_content")

    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
