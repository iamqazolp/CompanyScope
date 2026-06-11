import streamlit as st
import requests

st.set_page_config(page_title="CompanyScope", layout="wide")

st.title("CompanyScope")
st.markdown("Ask natural language questions about public companies' financial data and SEC filings. The agent uses RAG and specialized tools to fetch exact figures and quotes.")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_query" not in st.session_state:
    st.session_state.current_query = None

# Sidebar for configuration
with st.sidebar:
    st.header("Configuration")
    ticker = st.text_input("Target Ticker Symbol", value="AAPL").upper()
    api_url = st.text_input("FastAPI Backend URL", value="http://localhost:8000/ask")
    st.caption("The agent will automatically use the specified ticker as context for your questions.")
    
    st.divider()
    
    st.header("Example Questions")
    if st.button("What was the net income in 2023?"):
        st.session_state.current_query = "What was the net income in 2023?"
    if st.button("Summarize the risk factors from 2022."):
        st.session_state.current_query = "Summarize the risk factors from 2022."
        
    st.divider()
    
    st.header("Trick Question")
    st.caption("Test the agent's hallucination prevention:")
    if st.button("What is Apple's secret AI product?"):
        st.session_state.current_query = "What is Apple's secret AI product?"

# Display chat messages from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        # Render citations if they exist
        if message.get("citations"):
            with st.expander("View Citations & Sources"):
                for idx, cit in enumerate(message["citations"]):
                    if cit.get("type") == "numeric":
                        st.info(f"**{idx+1}. Numeric Fact:** {cit.get('concept')} for {cit.get('ticker')} in {cit.get('year')}")
                    elif cit.get("type") == "narrative":
                        st.success(f"**{idx+1}. SEC Filing ({cit.get('section')} - {cit.get('year')}):** \"{cit.get('quote')}\"")

user_input = st.chat_input(f"Ask about {ticker}'s revenue, risk factors, or management discussion...")
prompt = st.session_state.get("current_query") or user_input

# React to user input
if prompt:
    st.session_state.current_query = None
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Call FastAPI backend
    with st.chat_message("assistant"):
        with st.spinner(f"Analyzing {ticker} filings and financials..."):
            try:
                response = requests.post(api_url, json={"question": prompt, "ticker": ticker})
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if "error" in data:
                        st.error(f"Agent encountered an error: {data['error']}")
                        st.session_state.messages.append({"role": "assistant", "content": f"Error: {data['error']}"})
                        
                    elif data.get("needs_clarification"):
                        clarification = data["needs_clarification"]
                        st.warning(clarification)
                        st.session_state.messages.append({"role": "assistant", "content": clarification})
                        
                    else:
                        answer = data.get("answer", "No answer provided.")
                        citations = data.get("citations", [])
                        
                        st.markdown(answer)
                        
                        if citations:
                            with st.expander("View Citations & Sources"):
                                for idx, cit in enumerate(citations):
                                    if cit.get("type") == "numeric":
                                        st.info(f"**{idx+1}. Numeric Fact:** {cit.get('concept')} for {cit.get('ticker')} in {cit.get('year')}")
                                    elif cit.get("type") == "narrative":
                                        st.success(f"**{idx+1}. SEC Filing ({cit.get('section')} - {cit.get('year')}):** \"{cit.get('quote')}\"")
                                        
                        # Add assistant response to chat history
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": answer,
                            "citations": citations
                        })
                        
                elif response.status_code == 429:
                    error_msg = "Rate limit exceeded (10 requests/minute)! Please wait a moment."
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
                else:
                    st.error(f"Server Error {response.status_code}: {response.text}")
                    
            except requests.exceptions.ConnectionError:
                st.error(f"Failed to connect to the backend at {api_url}. Is the FastAPI server running?")

if __name__ == "__main__":
    import sys
    from streamlit.web import cli as stcli
    import streamlit.runtime as st_runtime
    
    if st_runtime.exists():
        pass
    else:
        sys.argv = ["streamlit", "run", sys.argv[0]]
        sys.exit(stcli.main())
