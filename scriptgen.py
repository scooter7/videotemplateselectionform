import streamlit as st
import pandas as pd
import openai
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

# Function to download CSV from GitHub
def load_template_data():
    url = "https://raw.githubusercontent.com/scooter7/videotemplateselectionform/main/Examples/examples.csv"
    return pd.read_csv(url)

# Load the template data
template_data = load_template_data()

# Function to generate text based on description and selected template
def generate_text(template_number, description, template_data):
    # Filter the template data based on the selected template number
    template_df = template_data[template_data['Template'] == f'Template {template_number}']

    output_text = []
    
    for idx, row in template_df.iterrows():
        for col in template_df.columns[2:]:  # Skip the first two columns (Template and Description)
            text_element = row[col]
            if pd.notna(text_element):  # Skip empty cells
                element_label = col.replace('_', ' ')  # Use column name as label
                # Ensure text adheres to description and format constraints
                customized_text = f"{element_label}: {text_element}"
                output_text.append(customized_text)

    # Join the generated text elements
    return '\n'.join(output_text)

def main():
    st.title("AI Script Generator")

    st.markdown("---")

    # Create radio buttons for templates 1-6
    template_number = st.radio("Select Template", [1, 2, 3, 4, 5, 6])

    # Add a field for entering a description
    description = st.text_area("Enter a description:")

    if st.button("Generate Text"):
        generated_text = generate_text(template_number, description, template_data)
        st.text_area("Generated Content", generated_text, height=300)

        # Download generated content
        st.download_button(
            label="Download as Text",
            data=generated_text,
            file_name=f"Template_{template_number}_Content.txt",
            mime="text/plain"
        )

    st.markdown("---")
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
