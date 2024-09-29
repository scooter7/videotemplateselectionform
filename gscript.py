import streamlit as st
import pandas as pd
import re
import openai
from streamlit_gsheets import GSheetsConnection

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

st.markdown(
    """
    <div class="logo-container">
        <img src="https://mir-s3-cdn-cf.behance.net/project_modules/1400/da17b078065083.5cadb8dec2e85.png" alt="Logo">
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="app-container">', unsafe_allow_html=True)

openai.api_key = st.secrets["openai_api_key"]

client = openai

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

@st.cache_data
def load_template_data():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    df = pd.read_csv(url)
    return df

template_data = load_template_data()

@st.cache_data
def load_google_sheet():
    conn = GSheetsConnection()
    sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    df = conn.read_sheet(sheet_url)
    return df

sheet_data = load_google_sheet()

def build_template_prompt(sheet_row, template_data):
    template_number = sheet_row['Template']
    description = sheet_row['Description']
    label = sheet_row['Label']
    template_data['Template'] = template_data['Template'].str.strip().str.lower()
    template_filter = f"template {template_number}".lower()
    template_row = template_data[template_data['Template'] == template_filter]
    prompt = f"Create content using the following description as the main focus:\n\n'{description}'\n\nUse the following structure and tone for guidance, but do not copy verbatim:\n\n"
    for col in template_row.columns[2:]:
        text_element = template_row[col].values[0]
        if pd.notna(text_element):
            prompt += f"{col}: {text_element}\n"
    return prompt, label

def generate_content(prompt, label):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    content = completion.choices[0].message.content.strip()
    content_clean = clean_text(content)
    return label + ": " + content_clean

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

def main():
    st.title("AI Script Generator from Google Sheets and Templates")
    st.markdown("---")

    if sheet_data.empty or template_data.empty:
        st.error("No data available from Google Sheets or Templates CSV.")
        return

    st.dataframe(sheet_data)

    if st.button("Generate Content from Google Sheets and Templates"):
        generated_contents = []
        for idx, row in sheet_data.iterrows():
            prompt, label = build_template_prompt(row, template_data)
            generated_content = generate_content(prompt, label)
            generated_contents.append(generated_content)
        
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
        st.session_state['social_content'] = generate_social_content(full_content, selected_channels)

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
