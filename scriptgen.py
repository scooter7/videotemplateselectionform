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

# Load the CSV data from GitHub (Templates CSV)
@st.cache_data
def load_template_data():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    try:
        df = pd.read_csv(url)
        st.write("CSV Data Loaded Successfully")
        return df
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()  # Return empty dataframe if failed

template_data = load_template_data()

# Function to build a prompt based on description and use the template for style/structure
def build_template_prompt(template_number, description, template_data):
    template_data['Template'] = template_data['Template'].str.strip().str.lower()
    template_filter = f"template {template_number}".lower()
    template_row = template_data[template_data['Template'] == template_filter]

    if template_row.empty:
        return f"No data found for Template {template_number}"

    prompt = f"Generate content focusing on the following description:\n\n'{description}'\n\nUse the tone, structure, and style from the following template as guidance but do not use any text from the template verbatim:\n\n"

    for col in template_row.columns[2:]:  # Skip the first two columns (Template and Description)
        text_element = template_row[col].values[0]
        if pd.notna(text_element):  # Only process non-empty cells
            prompt += f"{col}: {text_element}\n"

    return prompt

# Function to generate content using OpenAI's GPT-4o
def generate_content(description, template_number, template_data):
    prompt = build_template_prompt(template_number, description, template_data)
    completion = client.chat.completions.create(
        model="gpt-4o",  # Switched to GPT-4o model
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    
    # Process the response and insert column titles from the spreadsheet as text labels
    content = completion.choices[0].message.content.strip()
    content_clean = clean_text(content)
    
    # Get the column headings from the template as labels
    template_columns = template_data.columns[2:]  # Skip Template and Description columns
    content_lines = content_clean.split('\n')
    
    content_with_labels = ""
    for i, (col, line) in enumerate(zip(template_columns, content_lines)):
        content_with_labels += f"{col}: {line}\n"

    return content_with_labels

# Function to generate social media content for Facebook, LinkedIn, Instagram
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
        generated_content[channel] = clean_text(completion.choices[0].message.content.strip())  # Clean the content
    
    return generated_content

# Main function with session state handling
def main():
    st.title("AI Script Generator")
    st.markdown("---")

    # Initialize session state variables
    if 'generated_content' not in st.session_state:
        st.session_state['generated_content'] = ""
    if 'social_content' not in st.session_state:
        st.session_state['social_content'] = {}

    # Radio button for selecting the template (Templates 1-6)
    template_number = st.radio("Select Template", [1, 2, 3, 4, 5, 6])

    # Description field
    description = st.text_area("Enter a description:")

    # Generate main content
    if st.button("Generate Content"):
        if description and template_number:
            st.session_state['generated_content'] = generate_content(description, template_number, template_data)
            st.text_area("Generated Content", st.session_state['generated_content'], height=300, key="main_content")
            # Add download button for the generated content
            st.download_button(
                label="Download Generated Content",
                data=st.session_state['generated_content'],
                file_name="generated_content.txt",
                mime="text/plain"
            )
        else:
            st.error("Please select a template and enter a description.")

    # Social Media Checkboxes
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

    # Generate social media content
    if selected_channels and st.button("Generate Social Media Content"):
        st.session_state['social_content'] = generate_social_content(st.session_state['generated_content'], selected_channels)

    # Display social media content if available
    if st.session_state['social_content']:
        for channel, content in st.session_state['social_content'].items():
            st.subheader(f"{channel.capitalize()} Post")
            st.text_area(f"{channel.capitalize()} Content", content, height=200, key=f"{channel}_content")
            st.download_button(
                label=f"Download {channel.capitalize()} Content",
                data=content,
                file_name=f"{channel}_post.txt",
                mime="text/plain"
            )

    st.markdown("---")
    st.header("Revision Section")

    with st.expander("Revision Fields"):
        pasted_content = st.text_area("Paste Generated Content Here (for further revisions):", key="pasted_content")
        revision_requests = st.text_area("Specify Revisions Here:", key="revision_requests")

    if st.button("Revise Further"):
        revision_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": pasted_content},
            {"role": "user", "content": revision_requests}
        ]
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=revision_messages
        )
        revised_content = completion.choices[0].message.content.strip()
        revised_content_clean = clean_text(revised_content)  # Clean the revised content
        st.text(revised_content_clean)
        st.download_button("Download Revised Content", revised_content_clean, "revised_content_revision.txt", key="download_revised_content")

    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
