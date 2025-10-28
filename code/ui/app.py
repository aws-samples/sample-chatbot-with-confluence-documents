import streamlit as st
import streamlit.components.v1 as components
import uuid
from agentcore_client import AgentCoreClient

# Page config
st.set_page_config(
    page_title="Knowledge Base Chatbot",
    page_icon="🤖",
    layout="wide"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# Initialize AgentCore client
@st.cache_resource
def get_agentcore_client():
    return AgentCoreClient()

client = get_agentcore_client()

# Custom CSS for chat styling
st.markdown("""
<style>
.user-message {
    background: #007bff;
    color: white;
    padding: 8px 12px;
    border-radius: 15px 15px 5px 15px;
    margin: 5px 0 5px auto;
    max-width: 80%;
    word-wrap: break-word;
    display: block;
    text-align: right;
}

.assistant-message {
    background: #f1f3f4;
    color: #333;
    padding: 8px 12px;
    border-radius: 15px 15px 15px 5px;
    margin: 5px auto 5px 0;
    max-width: 80%;
    word-wrap: break-word;
    display: block;
}

.attached-article {
    background: #e8f4fd;
    border-left: 4px solid #007bff;
    padding: 10px;
    margin: 10px 0;
    border-radius: 5px;
}
</style>
""", unsafe_allow_html=True)

# Create two columns layout - make chat wider
col1, col2 = st.columns([1, 1])

# Main content in left column
with col1:
    st.title("Hello")
    st.write("Welcome to the Knowledge Base Chatbot! Use the chat panel on the right to ask questions.")

# Chat panel in right column
with col2:
    # Push chat to bottom using empty space
    st.markdown("<div style='height: 200px;'></div>", unsafe_allow_html=True)
    
    # Create chat container using Streamlit's native styling
    with st.container(border=True):
        st.markdown("**💬 Assistant**")
        
        # Chat messages area with fixed height
        with st.container(height=400):
            if not st.session_state.messages:
                st.markdown("*Start a conversation...*")
            else:
                for message in st.session_state.messages:
                    with st.chat_message(message["role"]):
                        if message["role"] == "assistant":
                            # Render assistant HTML in iframe with dynamic height via postMessage
                            html_with_resize = f"""
                            <!DOCTYPE html>
                            <html>
                            <head>
                                <style>
                                    body {{ 
                                        margin: 0; 
                                        padding: 10px; 
                                        max-width: 100%;
                                        overflow-y: auto;
                                        overflow-x: hidden;
                                        box-sizing: border-box;
                                    }}
                                    img {{
                                        max-width: 100% !important;
                                        height: auto !important;
                                        display: block;
                                    }}
                                </style>
                            </head>
                            <body>
                                {message["content"]}
                                <script>
                                    function sendHeight() {{
                                        const height = document.body.scrollHeight + 20;
                                        window.parent.postMessage({{
                                            type: "streamlit:setFrameHeight",
                                            height: height
                                        }}, "*");
                                    }}
                                    
                                    // Wait for all images to load before calculating height
                                    function waitForImages() {{
                                        const images = Array.from(document.getElementsByTagName('img'));
                                        
                                        if (images.length === 0) {{
                                            sendHeight();
                                            return;
                                        }}
                                        
                                        const imagePromises = images.map(img => {{
                                            if (img.complete) {{
                                                return Promise.resolve();
                                            }}
                                            return new Promise((resolve) => {{
                                                img.addEventListener('load', resolve);
                                                img.addEventListener('error', resolve);
                                            }});
                                        }});
                                        
                                        Promise.all(imagePromises).then(() => {{
                                            sendHeight();
                                        }});
                                    }}
                                    
                                    // Start waiting for images
                                    if (document.readyState === 'complete') {{
                                        waitForImages();
                                    }} else {{
                                        window.addEventListener('load', waitForImages);
                                    }}
                                    
                                    // Multiple fallback timeouts to catch any timing issues
                                    setTimeout(sendHeight, 500);
                                    setTimeout(sendHeight, 1000);
                                    setTimeout(sendHeight, 1500);
                                    setTimeout(sendHeight, 2000);
                                    setTimeout(sendHeight, 3000);
                                </script>
                            </body>
                            </html>
                            """
                            components.html(html_with_resize, height=600, scrolling=True)
                        else:
                            # User messages as plain text
                            st.write(message["content"])
        
        loading_placeholder = st.empty()

        # Chat input at bottom of container
        user_input = st.chat_input("Ask a question...")

# Handle user input immediately
if user_input:
    # Add user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # Get response from AgentCore (with built-in spinner)
    with st.empty():
        with loading_placeholder, st.spinner("⏳ Thinking..."):
            response = client.invoke_agent(user_input, st.session_state.session_id)

    # Add assistant response
    st.session_state.messages.append({"role": "assistant", "content": response})

    # Single rerun to refresh the display
    st.rerun()