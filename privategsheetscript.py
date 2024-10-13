import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time

# Function to load Google Sheet
def load_google_sheet(sheet_id):
    credentials_info = st.secrets["google_credentials"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    gc = gspread.authorize(credentials)
    
    try:
        sheet = gc.open_by_key(sheet_id).sheet1
        data = pd.DataFrame(sheet.get_all_records())
        return data, sheet
    except gspread.SpreadsheetNotFound:
        st.error(f"Spreadsheet with ID '{sheet_id}' not found.")
        return pd.DataFrame(), None

# Function to log progress and track any failures
def log_step(message):
    st.write(message)

# Function to transfer generated content to the Google Sheet
def update_google_sheet_with_content(sheet, row_index, col_letter, content):
    try:
        log_step(f"Updating cell {col_letter}{row_index} with content: '{content}'")
        sheet.update_acell(f'{col_letter}{row_index}', content)
        time.sleep(1)  # Adding a delay to avoid rate-limiting
    except Exception as e:
        log_step(f"Error updating cell {col_letter}{row_index}: {e}")

# Main function to handle content generation and transfer
def main():
    st.title("AI Content Generator with Google Sheet Transfer")
    
    # Load the Google Sheet
    sheet_id = '1fZs6GMloaw83LoxaX1NYIDr1xHiKtNjyJyn2mKMUvj8'
    sheet_data, sheet = load_google_sheet(sheet_id)
    
    if sheet_data.empty:
        st.error("No data available from the Google Sheet.")
        return
    
    st.dataframe(sheet_data)  # Display the Google Sheet data for review
    
    # Dummy content generated for testing purposes
    dummy_generated_content = {
        "Text01": "Excellence in Design",
        "Text01-1": "Excellence in",
        "Text01-2": "Design",
        "Text02": "Howard Commons WI",
        "Text02-1": "Howard",
        "Text02-2": "Commons WI"
    }

    if st.button("Transfer Content to Google Sheet"):
        # Simulate content transfer for the first Job ID in the sheet
        row_index = 2  # Assuming we're transferring to the second row as an example
        
        # Define column mappings for each section
        column_mappings = {
            "Text01": "H", "Text01-1": "I", "Text01-2": "J", 
            "Text02": "N", "Text02-1": "O", "Text02-2": "P"
        }
        
        # Transfer the content to the sheet
        for section_name, content in dummy_generated_content.items():
            col_letter = column_mappings.get(section_name)
            if col_letter:
                update_google_sheet_with_content(sheet, row_index, col_letter, content)
            else:
                log_step(f"No column mapping found for section: {section_name}")

if __name__ == "__main__":
    main()
