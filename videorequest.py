import streamlit as st
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Function to send email
def send_email(first_name, last_name, email, description, template):
    sender_email = "james.vineburgh@magellaneducation.co"
    receiver_email = "scooter.vineburgh@gmail.com"
    password = "VictoriaJames7!"

    # Create the email content
    message = MIMEMultipart("alternative")
    message["Subject"] = "New Campaign Submission"
    message["From"] = sender_email
    message["To"] = receiver_email

    text = f"""
    New Campaign Submission:

    First Name: {first_name}
    Last Name: {last_name}
    Corporate Email Address: {email}
    Description of Campaign: {description}
    Selected Video Template: {template}
    """

    part = MIMEText(text, "plain")
    message.attach(part)

    # Connect to the server and send the email
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        return "Email sent successfully!"
    except Exception as e:
        return f"Error sending email: {e}"

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
    result = send_email(first_name, last_name, email, description, template)
    st.write(result)
