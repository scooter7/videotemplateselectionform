import streamlit as st
import pandas as pd
import re
from anthropic import Anthropic

# Initialize Anthropic client
anthropic_client = Anthropic(api_key=st.secrets["anthropic_api_key"])

# Function to clean text
def clean_text(text):
    text = re.sub(r'\*\*', '', text)
    emoji_pattern = re.compile(
        "["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text)

# Load template data
@st.cache_data
def load_template_data():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    df = pd.read_csv(url)
    return df

template_data = load_template_data()

# Build prompt based on template
def build_template_prompt(template_number, description, template_data):
    template_data['Template'] = template_data['Template'].str.strip().str.lower()
    template_filter = f"template {template_number}".lower()
    template_row = template_data[template_data['Template'] == template_filter]

    if template_row.empty:
        return f"No data found for Template {template_number}"

    prompt = f"Create content based on the following description:\n\n{description}\n\nUse the following structure:\n\n"
    for col in template_row.columns[2:]:
        text_element = template_row[col].values[0]
        if pd.notna(text_element):
            prompt += f"{col}: {text_element}\n"

    return prompt

# Generate main content
def generate_content(description, template_number, template_data):
    prompt = build_template_prompt(template_number, description, template_data)
    response = anthropic_client.messages.create(
        model="claude-3-5-sonnet-20240620",
        messages=[
            {"role": "user", "content": prompt}
        ],
        system="You are a helpful assistant.",
        max_tokens=1000
    )
    # Extract the assistant's reply from response.completion
    content = response.completion.strip()
    content_clean = clean_text(content)
    return content_clean

# Generate social media content
def generate_social_content(main_content, selected_channels):
    generated_content = {}
    for channel in selected_channels:
        tone_url = {
            "facebook": "https://www.facebook.com/ShiveHattery",
            "linkedin": "https://www.linkedin.com/company/shive-hattery/",
            "instagram": "https://www.instagram.com/shivehattery/"
        }.get(channel, "")
        
        prompt = f"Generate a {channel.capitalize()} post based on the following content:\n{main_content}\nUse a tone similar to the posts on {tone_url}."
        
        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20240620",
            messages=[
                {"role": "user", "content": prompt}
            ],
            system="You are a helpful assistant.",
            max_tokens=1000
        )
        # Extract the assistant's reply
        content = response.completion.strip()
        generated_content[channel] = clean_text(content)
    return generated_content

# Main function
def main():
    st.title("AI Script Generator")
    st.markdown("---")

    if 'generated_content' not in st.session_state:
        st.session_state['generated_content'] = ""
    if 'social_content' not in st.session_state:
        st.session_state['social_content'] = {}

    template_number = st.radio("Select Template", [1, 2, 3, 4, 5, 6])
    description = st.text_area("Enter a description:")

    if st.button("Generate Content"):
        if description and template_number:
            st.session_state['generated_content'] = generate_content(description, template_number, template_data)
            st.text_area("Generated Content", st.session_state['generated_content'], height=300)
            st.download_button(
                label="Download Generated Content",
                data=st.session_state['generated_content'],
                file_name="generated_content.txt",
                mime="text/plain"
            )
        else:
            st.error("Please select a template and enter a description.")

    if st.session_state['generated_content']:
        st.text_area("Generated Content", st.session_state['generated_content'], height=300)

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

    if selected_channels and st.button("Generate Social Media Content"):
        st.session_state['social_content'] = generate_social_content(st.session_state['generated_content'], selected_channels)

        for channel, content in st.session_state['social_content'].items():
            st.subheader(f"{channel.capitalize()} Post")
            st.text_area(f"{channel.capitalize()} Content", content, height=200)
            st.download_button(
                label=f"Download {channel.capitalize()} Content",
                data=content,
                file_name=f"{channel}_post.txt",
                mime="text/plain"
            )

    st.markdown("---")
    st.header("Revision Section")

    with st.expander("Revision Fields"):
        pasted_content = st.text_area("Paste Generated Content Here (for further revisions):")
        revision_requests = st.text_area("Specify Revisions Here:")

    if st.button("Revise Further"):
    revision_prompt = f"{pasted_content}\n\n{revision_requests}"

    response = anthropic_client.messages.create(
        model="claude-3-5-sonnet-20240620",
        messages=[
            {"role": "user", "content": revision_prompt}
        ],
        system="You are a helpful assistant.",
        max_tokens=1000
    )

    # Extract the assistant's reply
    revised_content = response.completion.strip()
    revised_content = clean_text(revised_content)
    st.text_area("Revised Content", revised_content, height=300)
    st.download_button(
        label="Download Revised Content",
        data=revised_content,
        file_name="revised_content.txt",
        mime="text/plain"
    )

