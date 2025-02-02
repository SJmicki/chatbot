import streamlit as st
import pandas as pd
import numpy as np
import time
import requests
import re
from bs4 import BeautifulSoup
from openai import OpenAI
from webscrape import WebScrape

# create request header
headers = {'User-Agent': "Kevin.Peterson@bainbridge.com"}

st.title("Summarize MD&A section of your favorite stock's financial reports")
st.text("Note: current version only reads one report at a time. When selecting Nth latest report, it means you are selecting THE Nth latest report not latest N reports.")
ticker = st.text_input("Ticker name (UPPER case)", "")
filing_type = st.selectbox("Select filing type", ("10-K", "10-Q"),
                           index=None,
                            placeholder="i.e 10-K, 10-Q",)
latest_nth_report = st.slider("Nth latest report.", 1, 20) - 1

if st.button("submit"):
    filing = WebScrape(headers, ticker, filing_type, latest_nth_report)
    st.session_state.mda = filing.extract_mda_section()
    st.session_state.ticker = filing.ticker
    st.session_state.report_name = filing.report_name
    st.session_state.basic_info = f"""
I will ask questions related {st.session_state['ticker']}. If I refer to financials without specification, it means the financial statements as of {st.session_state['report_name']}. Respond 'Got it' if you understand.
"""

st.write(
    "To use this app, you need to provide an OpenAI API key, which you can get [here](https://platform.openai.com/account/api-keys). "
)

# Ask user for their OpenAI API key via `st.text_input`.
# Alternatively, you can store the API key in `./.streamlit/secrets.toml` and access it
# via `st.secrets`, see https://docs.streamlit.io/develop/concepts/connections/secrets-management

prompt_prefix = """
You are an financial investment expert with years of experience in the equity research space. Only answer my questions when I explicitly ask so. When you respond, provide strctured responses that answers inquiries in a comprehensive manner that considers both profits and risks.
"""

openai_api_key = st.text_input("OpenAI API Key", type="password")
if not openai_api_key:
    st.info("Please add your OpenAI API key to continue.", icon="🗝️")
else:

    # Create an OpenAI client.
    client = OpenAI(api_key=openai_api_key)

    # Create a session state variable to store the chat messages. This ensures that the messages persist across reruns.
    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.messages.append({"role": "system", "content": prompt_prefix})
        st.session_state.messages.append({"role": "user", "content": st.session_state.basic_info})

    # Display the existing chat messages via `st.chat_message`.
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"][:5000])
    
    # Create a chat input field to allow the user to enter a message. This will display
    # automatically at the bottom of the page.
    if prompt := st.chat_input("What is up?"):
        
        # Store and display the current prompt.
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

    if st.button("MDA Analysis"):
        mda_input = f"""You will be asked to evaluate the Management Discussion and Analysis section of public company financial statements. 
Based on the report input and your financial expertise, provide 1) a summary of the MDA, 2) sentiment analysis of the report, 3) key highlights and low lights of the report. 
This MDA analysis is related to {st.session_state['ticker']} - {st.session_state['report_name']}. Here is the report: {st.session_state['mda']}"""
        st.session_state.messages.append({"role": "user", "content": mda_input})

        # Generate a response using the OpenAI API.
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages
                ],
            stream=True,
        )
    else:    
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages
                ],
            stream=True,
        )

        # Stream the response to the chat using `st.write_stream`, then store it in session state.
    with st.chat_message("assistant"):
        response = st.write_stream(stream)
    st.session_state.messages.append({"role": "assistant", "content": response})