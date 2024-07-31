import streamlit as st
import pandas as pd
import openai

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
        <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/East_Carolina_University.svg/1280px-East_Carolina_University.svg.png" alt="Logo">
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="app-container">', unsafe_allow_html=True)

# Load Streamlit secrets for API keys
openai.api_key = st.secrets["openai_api_key"]

# Function to generate content using OpenAI
def generate_content(description, template):
    template_map = {
        1: "200 characters broken into two paragraphs.",
        2: "400 characters broken into four paragraphs.",
        3: "600 characters broken into six paragraphs.",
        4: "800 characters broken into eight paragraphs."
    }
    
    prompt = (
        f"Create content based on the following description:\n\n"
        f"{description}\n\n"
        f"Template: {template_map[template]}"
    )

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message["content"].strip()

def main():
    st.title("AI Content Generator")
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
            template = int(row["template"])

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
        st.text(revised_content)
        st.download_button("Download Revised Content", revised_content, "revised_content_revision.txt", key="download_revised_content")

    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
