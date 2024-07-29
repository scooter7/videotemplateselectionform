import streamlit as st
import boto3
import pandas as pd
from io import StringIO

# Load secrets
aws_access_key_id = st.secrets["AWS"]["aws_access_key_id"]
aws_secret_access_key = st.secrets["AWS"]["aws_secret_access_key"]
bucket_name = st.secrets["AWS"]["bucket_name"]
object_key = st.secrets["AWS"]["object_key"]

# Function to read CSV from S3
def read_csv_from_s3(bucket, key, access_key, secret_key):
    s3_client = boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )
    try:
        csv_obj = s3_client.get_object(Bucket=bucket, Key=key)
        body = csv_obj['Body']
        csv_string = body.read().decode('utf-8')
        return pd.read_csv(StringIO(csv_string))
    except s3_client.exceptions.NoSuchKey:
        return pd.DataFrame(columns=["first_name", "last_name", "email", "description", "template"])

# Function to upload CSV to S3
def upload_to_s3(dataframe, bucket, key, access_key, secret_key):
    csv_buffer = StringIO()
    dataframe.to_csv(csv_buffer, index=False)
    
    s3_resource = boto3.resource(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )
    
    s3_resource.Object(bucket, key).put(Body=csv_buffer.getvalue())

# Streamlit app
st.title("Campaign Submission Form")

with st.form(key='campaign_form'):
    first_name = st.text_input("First Name")
    last_name = st.text_input("Last Name")
    email = st.text_input("Corporate Email Address")
    description = st.text_area("Description of Campaign")

    st.write("### Select a Video Template:")
    
    template1 = st.checkbox("Template 1", key='template1')
    st.video("https://youtu.be/QlbZ-FQYJlk", format="video/mp4", start_time=0)
    
    template2 = st.checkbox("Template 2", key='template2')
    st.video("https://youtu.be/e2Dey2DS784, format="video/mp4", start_time=0)
    
    template3 = st.checkbox("Template 3", key='template3')
    st.video("https://youtu.be/A3ycwztkUHM", format="video/mp4", start_time=0)
    
    template4 = st.checkbox("Template 4", key='template4')
    st.video("https://youtu.be/61B7-zPYlTU", format="video/mp4", start_time=0)
    
    submit_button = st.form_submit_button(label='Submit')

if submit_button:
    selected_template = None
    if template1:
        selected_template = "Template 1"
    elif template2:
        selected_template = "Template 2"
    elif template3:
        selected_template = "Template 3"
    elif template4:
        selected_template = "Template 4"
    
    if selected_template is None:
        st.error("Please select one video template.")
    else:
        # Read existing data from S3
        existing_df = read_csv_from_s3(bucket_name, object_key, aws_access_key_id, aws_secret_access_key)
        
        # Create a DataFrame for the new data
        new_data = {
            "first_name": [first_name],
            "last_name": [last_name],
            "email": [email],
            "description": [description],
            "template": [selected_template]
        }
        new_df = pd.DataFrame(new_data)
        
        # Append new data to existing data
        updated_df = pd.concat([existing_df, new_df], ignore_index=True)
        
        # Upload the updated data back to S3
        upload_to_s3(updated_df, bucket_name, object_key, aws_access_key_id, aws_secret_access_key)
        
        st.success("Data submitted and uploaded to S3 successfully!")
