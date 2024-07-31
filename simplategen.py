import streamlit as st
import pandas as pd
import openai
import re

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

# Function to generate content using OpenAI
def generate_content(description, template):
    template_map = {
        1: {"prompt": "200 characters broken into two paragraphs.", "limit": 200},
        2: {"prompt": "400 characters broken into four paragraphs.", "limit": 400},
        3: {"prompt": "600 characters broken into six paragraphs.", "limit": 600},
        4: {"prompt": "800 characters broken into eight paragraphs.", "limit": 800}
    }
    
    prompt = (
        f"Create content based on the following description:\n\n"
        f"{description}\n\n"
        f"Template: {template_map[template]['prompt']}"
    )

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    
    content = response.choices[0].message["content"].strip()
    content_no_emojis = remove_emojis(content)
    
    # Ensure the content adheres to the character limit
    if len(content_no_emojis) > template_map[template]['limit']:
        content_no_emojis = content_no_emojis[:template_map[template]['limit']].rsplit(' ', 1)[0]
    
    return content_no_emojis

def main():
    st.title("AI Script Generator")
    st.markdown("---")

    # Initialize the session state for generated pages
    if 'generated_pages' not in st.session_state:
        st.session_state.generated_pages = []

    uploaded_file = st.file_uploader("Upload CSV", type="csv")

    if uploaded_file and st.button("Generate Content"):
        # Read the uploaded CSV file
        csv_data = pd.read_csv(uploaded_file)

        # Generate content for each row in the CSV
        generated_pages = []
        for _, row in csv_data.iterrows():
            if str(row.get("Completed", "")).strip().lower() == "yes":
                continue
            
            first_name = row["first_name"]
            last_name = row["last_name"]
            email = row["email"]
            description = row["description"]
            template_str = row["template"]
            template = int(template_str.split()[-1])  # Extract the numeric part from the template string

            generated_content = generate_content(description, template)
            generated_pages.append((first_name, last_name, email, description, generated_content))

        st.session_state.generated_pages = generated_pages

    if st.session_state.generated_pages:
        # Display and download generated content
        for idx, (first_name, last_name, email, description, content) in enumerate(st.session_state.generated_pages):
            st.subheader(f"{first_name} {last_name} - {email}")
            st.text_area("Generated Content", content, height=300)

            # Create a download button for the generated content
            content_text = f"{first_name} {last_name} - {email}\n\n{description}\n\n{content}"
            st.download_button(
                label="Download as Text",
                data=content_text,
                file_name=f"{first_name}_{last_name}.txt",
                mime="text/plain",
                key=f"download_button_{idx}"
            )

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
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=revision_messages)
        revised_content = response.choices[0].message["content"].strip()
        revised_content_no_emojis = remove_emojis(revised_content)
        st.text(revised_content_no_emojis)
        st.download_button("Download Revised Content", revised_content_no_emojis, "revised_content_revision.txt", key="download_revised_content")

    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()