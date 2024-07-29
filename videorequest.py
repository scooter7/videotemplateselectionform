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

# Authentication
def check_login(username, password):
    return username == "scooter.vineburgh@gmail.com" and password == "Simplate1!"

# Streamlit app with navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Submission", "Admin"])

if page == "Submission":
    st.title("Campaign Submission Form")
    with st.form(key='campaign_form'):
        first_name = st.text_input("First Name")
        last_name = st.text_input("Last Name")
        email = st.text_input("Corporate Email Address")
        description = st.text_area("Description of Campaign")

        st.write("### Select a Video Template:")
        
        # Display videos in columns
        col1, col2 = st.columns(2)
        with col1:
            st.video("https://youtu.be/QlbZ-FQYJlk", format="video/mp4", start_time=0)
            st.write("Template 1")
        with col2:
            st.video("https://youtu.be/e2Dey2DS784", format="video/mp4", start_time=0)
            st.write("Template 2")
            
        col3, col4 = st.columns(2)
        with col3:
            st.video("https://youtu.be/A3ycwztkUHM", format="video/mp4", start_time=0)
            st.write("Template 3")
        with col4:
            st.video("https://youtu.be/61B7-zPYlTU", format="video/mp4", start_time=0)
            st.write("Template 4")
        
        selected_template = st.radio(
            label="Choose one of the following templates:",
            options=["Template 1", "Template 2", "Template 3", "Template 4"]
        )

        submit_button = st.form_submit_button(label='Submit')

    if submit_button:
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

elif page == "Admin":
    st.title("Admin Login")
    admin_email = st.text_input("Email")
    admin_password = st.text_input("Password", type="password")
    login_button = st.button("Login")

    if login_button:
        if check_login(admin_email, admin_password):
            st.success("Login successful!")
            st.title("Admin Dashboard")
            st.write("Current Submissions:")
            data = read_csv_from_s3(bucket_name, object_key, aws_access_key_id, aws_secret_access_key)
            st.dataframe(data)
        else:
            st.error("Invalid email or password. Please try again.")
