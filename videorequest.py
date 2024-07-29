import streamlit as st
import boto3
import pandas as pd
from io import StringIO

# Load AWS credentials from Streamlit secrets
aws_access_key_id = st.secrets["AWS"]["aws_access_key_id"]
aws_secret_access_key = st.secrets["AWS"]["aws_secret_access_key"]
bucket_name = st.secrets["AWS"]["bucket_name"]
object_key = st.secrets["AWS"]["object_key"]

# Function to upload data to S3
def upload_to_s3(dataframe, bucket, key):
    csv_buffer = StringIO()
    dataframe.to_csv(csv_buffer, index=False)
    s3_resource = boto3.resource(
        's3',
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
    )
    s3_resource.Object(bucket, key).put(Body=csv_buffer.getvalue())

# Streamlit app
st.title("Campaign Submission Form")

with st.form(key='campaign_form'):
    first_name = st.text_input("First Name")
    last_name = st.text_input("Last Name")
    email = st.text_input("Corporate Email Address")
    description = st.text_area("Description of Campaign")
    template = st.selectbox("Select Video Template", ["Template 1", "Template 2", "Template 3", "Template 4"])

    submit_button = st.form_submit_button(label='Submit')

if submit_button:
    # Create a DataFrame from the form inputs
    data = {
        'first_name': [first_name],
        'last_name': [last_name],
        'email': [email],
        'description': [description],
        'template': [template]
    }
    df = pd.DataFrame(data)
    
    # Check if the CSV file already exists in S3
    s3_client = boto3.client(
        's3',
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
    )
    
    try:
        s3_client.head_object(Bucket=bucket_name, Key=object_key)
        # File exists, so read it and append new data
        obj = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        existing_df = pd.read_csv(obj['Body'])
        df = pd.concat([existing_df, df], ignore_index=True)
    except s3_client.exceptions.NoSuchKey:
        # File does not exist, so create a new one
        pass
    
    # Upload the updated DataFrame to S3
    upload_to_s3(df, bucket_name, object_key)
    
    st.success("Form submitted successfully and data saved to S3!")

