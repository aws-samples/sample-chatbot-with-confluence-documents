import json
import os
import boto3
from botocore.config import Config
import re
import bleach
from typing import Dict, List, TypedDict
# nosemgrep: ai.python.detect-langchain
from langchain_core.messages import HumanMessage, SystemMessage
# nosemgrep: ai.python.detect-langchain
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient
from langchain_aws import ChatBedrock

# Initialize AgentCore app
app = BedrockAgentCoreApp()

# Global configuration
config = {}
ssm_client = boto3.client('ssm')
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime')
# Configure S3 client with Signature Version 4 for KMS-encrypted objects
s3_client = boto3.client('s3', config=Config(signature_version='s3v4'))
memory_client = None
# Default fallback - will be overridden by config
knowledge_base_top_N = 3

class ChatbotState(TypedDict):
    memory_context: str
    user_input: str
    enhanced_input: str
    tool_calling: bool
    kb_results: List[Dict]
    llm_response: str
    final_response: str
    user_id: str
    session_id: str

def load_config():
    """Load configuration from SSM Parameter Store"""
    global config, memory_client
    try:
        parameter_name = os.environ.get('SSM_PARAMETER_NAME', '/confluence-bedrock/dev/config')
        response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)
        config = json.loads(response['Parameter']['Value'])
        
        # Validate required configuration
        aws_region = config.get('aws_region')
        if not aws_region:
            # Use boto3 session region as fallback
            session = boto3.Session()
            aws_region = session.region_name
            if not aws_region:
                raise ValueError("AWS region not specified in config and no default region found in boto3 session. Please set aws_region in SSM parameter or configure AWS CLI with default region.")
            config['aws_region'] = aws_region
        
        # Validate LLM model ID is specified
        llm_model_id = config.get('llm_model_id')
        if not llm_model_id:
            raise ValueError("LLM model ID not specified in config. Please set llm_model_id in SSM parameter to avoid using hardcoded US models.")
        
        memory_client = MemoryClient(region_name=aws_region)
        
    except Exception as e:
        print(f"Error loading config: {e}")
        # For development/testing only - fail fast in production
        if os.environ.get('ENVIRONMENT') == 'development':
            session = boto3.Session()
            aws_region = session.region_name
            if not aws_region:
                raise ValueError("Development mode: AWS region not found. Please configure AWS CLI with default region.")
            
            config = {
                'knowledge_base_id': os.environ.get('KNOWLEDGE_BASE_ID', ''),
                'knowledge_base_top_n': 3,
                'aws_region': aws_region
            }
            memory_client = MemoryClient(region_name=aws_region)
        else:
            raise ValueError(f"Failed to load configuration from SSM: {e}")

def load_memory_context(actor_id: str, session_id: str) -> str:
    """Load memory context from AgentCore Memory"""
    try:
        memory_id = config.get('memory_id')
        print(f"Memory ID: {memory_id}")
        if not memory_id or not memory_client:
            return ""
        
        events = memory_client.list_events(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            max_results=5
        )
        
        context_parts = []
        for event in reversed(events[-3:]):
            if 'payload' in event:
                for payload_item in event['payload']:
                    if 'conversational' in payload_item:
                        conv = payload_item['conversational']
                        role = conv.get('role', '').upper()
                        content = conv.get('content', {}).get('text', '').strip()
                        if content and role in ['USER', 'ASSISTANT']:
                            context_parts.append(f"\n<role>{role}</role>: <content><{content}</content>")
        
        return "\n".join(context_parts)
    except Exception as e:
        print(f"Error loading memory: {e}")
        return ""

@tool
def search_knowledge_base_tool(query: str) -> List[Dict]:
    """Search the knowledge base for relevant articles.
    
    Args:
        query: Succinct search query capturing user intent with conversation context
    """
    return search_knowledge_base(query)

def search_knowledge_base(query: str) -> List[Dict]:
    """Search Bedrock Knowledge Base"""
    try:
        kb_id = config.get("knowledge_base_id", "")
        if not kb_id:
            return []
        
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={'text': query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': config.get("knowledge_base_top_n", knowledge_base_top_N)
                }
            }
        )
        
        results = []
        for result in response.get('retrievalResults', []):
            results.append({
                'content': result.get('content', {}).get('text', ''),
                'score': result.get('score', 0),
                'metadata': result.get('metadata', {})
            })
        
        return results
    except Exception as e:
        print(f"Error searching KB: {e}")
        return []

def format_response_html(response_content: str, kb_results: List[Dict]) -> str:

    """Format response by replacing article references with actual content"""
    def replace_article_ref(match):
        article_num = int(match.group(1))
        if article_num < len(kb_results):
            article_content = kb_results[article_num]['content']
            html_content = markdown_to_html(article_content)
            return f'<br/><br/><div class="attached-article" style="padding: 5px; background-color: #f2f2f2; border-style:solid; border-color: orange; border-width: 1px">{html_content}</div>'
        return ""
    
    formatted_html = re.sub(r'<article ref=(\d+)/>', replace_article_ref, response_content)
    return f'<div>{formatted_html}</div>'

def sanitize_html(html: str) -> str:
    """Sanitize HTML to prevent XSS attacks"""
    # Define allowed tags and attributes
    allowed_tags = [
        'p', 'br', 'strong', 'em', 'b', 'i', 'u',
        'ul', 'ol', 'li',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'a', 'img',
        'div', 'span',
        'code', 'pre', 'blockquote',
        'table', 'thead', 'tbody', 'tr', 'th', 'td'
    ]
    
    allowed_attributes = {
        'a': ['href', 'title'],
        'img': ['src', 'alt', 'style'],
        'div': ['class'],
        'span': ['class']
    }
    
    # Sanitize the HTML
    clean_html = bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attributes,
        strip=True
    )
    
    return clean_html

def markdown_to_html(markdown_text: str) -> str:
    """Convert markdown to HTML with S3 presigned URLs"""
    html = markdown_text.strip()
    
    # Convert double spaces to double line breaks (Bedrock KB normalizes newlines to spaces)
    html = html.replace('  ', '<br><br>')
    
    # Headers
    html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    
    # Bold/italic
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
    
    # Lists
    html = re.sub(r'^- (.*?)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', html, flags=re.DOTALL)
    
    # Images with S3 presigned URLs
    def replace_image_ref(match):
        s3_path = match.group(1)
        try:
            if s3_path.startswith('s3://'):
                path_parts = s3_path[5:].split('/', 1)
                if len(path_parts) == 2:
                    bucket_name, key = path_parts
                    presigned_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': bucket_name, 'Key': key},
                        ExpiresIn=3600
                    )
                    return f'<img src="{presigned_url}" alt="Tutorial Image" style="max-width: 100%; height: auto; margin: 10px 0;">'
            return f'<div><em>Image: {s3_path}</em></div>'
        except Exception as e:
            print(f"Error generating presigned URL: {e}")
            return f'<div><em>Image: {s3_path}</em></div>'
    
    html = re.sub(r'!\[.*?\]\(([^)]+)\)', replace_image_ref, html)
    html = html.replace('\n', '<br>')
    
    if not re.match(r'^\s*<[^>]+>', html):
        html = f'<div>{html}</div>'
    
    # Sanitize HTML to prevent XSS attacks
    html = sanitize_html(html)
    
    return html

def create_agent():
    """Create LangGraph agent with conditional KB search"""
    llm = ChatBedrock(
        model_id=config.get('llm_model_id'),
        region_name=config.get('aws_region'),
        model_kwargs={"temperature": 0.1}
    )
    
    # Bind tools to LLM
    tools = [search_knowledge_base_tool]
    llm_with_tools = llm.bind_tools(tools)
    
    def memory_load_node(state: ChatbotState) -> Dict:
        memory_context = load_memory_context(state.get("user_id"), state.get("session_id"))
        user_input = state.get("user_input", "")
        enhanced_input = f"<context>: {memory_context}</context>\n\n\n<question>: {user_input}</question>" if memory_context else user_input
        return {
            "memory_context": memory_context,
            "enhanced_input": enhanced_input,
            "tool_calling": False,
            "kb_results": []
        }
    
    def llm_decision_node(state: ChatbotState) -> Dict:
        enhanced_input = state.get("enhanced_input", "")
        
        system_content = """You are a helpful assistant that answers questions using tutorial documentation.

DECISION LOGIC:
- If you can answer from conversation context alone → respond directly with complete HTML answer
- If you need new information → use search_knowledge_base_tool with succinct, context-aware query
- For follow-ups about previous answers → you may skip search_knowledge_base_tool if context sufficient

When about to use search_knowledge_base_tool tool:
- Generate context-aware, succinct search query that captures user intent
- Tool will return articles for your next response

When providing final response by skipping tool:
- Provide complete HTML-formatted answer
- If the article to be referenced is already in the conversation context, there is no need to append <article ref=N/> at the end of your respond

Always format responses in HTML."""
        
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=enhanced_input)
        ]
        
        response = llm_with_tools.invoke(messages)
        
        # Check if tool was called
        tool_calls = response.tool_calls
        
        return {
            "tool_calling": bool(tool_calls and len(tool_calls) > 0),
            "llm_response": response
        }
    
    def search_kb_node(state: ChatbotState) -> Dict:
        toolNode = ToolNode(tools)
        response = toolNode.invoke({"messages": [state["llm_response"]]})

        if response and 'messages' in response and len(response['messages']) > 0:
            try:
                return {
                    "tool_calling": False,
                    "kb_results": json.loads(response['messages'][0].content)
                }
            except Exception as e:
                print(f"Error parsing tool response: {e}")
                print(f"Knowledge Bases response's messages were {response['messages']}")
                return {
                    "tool_calling": False,
                    "kb_results": []
                }
        else:
            return {
                "tool_calling": False,
                "kb_results": []
            }
    
    def final_response_node(state: ChatbotState) -> Dict:
        enhanced_input = state.get("enhanced_input", "")
        kb_results = state.get("kb_results", [])

        # Format KB results for LLM
        kb_context = "\n".join([f"Article {i}: {result['content'][:500]}..." 
                               for i, result in enumerate(kb_results)])
        
        system_content = """You are a helpful assistant. Generate a final answer using the knowledge base results.

INSTRUCTIONS:
- Provide complete HTML-formatted answer (NO MARKDOWN). You can use <b> for bold and <ul><li> for items.
- If you are basing your answer from 1 or more articles returned from knowledge base, append <article ref=N/> at the end to attach reference on the article from the tool. N starts from 0. 
- If there are multiple articles to be referenced, you can have multiple <article> elements
- Each index of article reference must not occur more than once in your answer
- Later (at post-processing) the <article> elements will be replaced with the actual article's content for display to user

Knowledge Base Results:
""" + kb_context
        
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=enhanced_input)
        ]
        
        response = llm.invoke(messages)
        return {"llm_response": response}
    
    def post_processing_node(state: ChatbotState) -> Dict:
        llm_response = state.get("llm_response", "")
        kb_results = state.get("kb_results", [])
        
        # Format response with article references
        formatted_response = format_response_html(llm_response.content, kb_results)
        
        return {"final_response": formatted_response}
    
    def memory_save_node(state: ChatbotState) -> Dict:
        try:
            memory_id = config.get('memory_id')
            if memory_id and memory_client:
                user_input = state.get("user_input", "")
                final_response = state.get("final_response", "")
                user_id = state.get("user_id", "default_user")
                session_id = state.get("session_id", "default_session")
                
                if user_input and final_response:
                    memory_client.create_event(
                        memory_id=memory_id,
                        actor_id=user_id,
                        session_id=session_id,
                        messages=[
                            (user_input, "USER"),
                            (final_response, "ASSISTANT")
                        ]
                    )
        except Exception as e:
            print(f"Error saving memory: {e}")
        
        return {}
    
    def need_kb_search(state: ChatbotState) -> str:
        """Route based on whether tool was called"""
        if state.get("tool_calling", False):
            return True
        else:
            return False
    
    # Build graph
    graph = StateGraph(ChatbotState)
    
    # Add nodes
    graph.add_node("memory_load", memory_load_node)
    graph.add_node("llm_decision", llm_decision_node)
    graph.add_node("tools", search_kb_node)
    graph.add_node("final_response", final_response_node)
    graph.add_node("post_processing", post_processing_node)
    graph.add_node("memory_save", memory_save_node)
    
    # Add edges
    graph.add_edge("memory_load", "llm_decision")
    graph.add_conditional_edges("llm_decision", need_kb_search, {
        True: "tools",
        False: "post_processing"
    })
    graph.add_edge("tools", "final_response")
    graph.add_edge("final_response", "post_processing")
    graph.add_edge("post_processing", "memory_save")
    graph.add_edge("memory_save", END)
    
    graph.set_entry_point("memory_load")
    
    return graph.compile()

# Load configuration and create agent
load_config()
agent = create_agent()

@app.entrypoint
def agent_invocation(payload):
    """AgentCore entrypoint"""
    try:
        user_input = payload.get("prompt") or payload.get("question") or payload.get("inputText", "")
        user_id = payload.get("user_id", "default_user")
        session_id = payload.get("session_id", "default_session")

        if not user_input:
            return {"result": "<p>Please provide a question.</p>"}
        
        initial_state = {
            "memory_context": "",
            "user_input": user_input,
            "enhanced_input": "",
            "tool_called": False,
            "kb_results": [],
            "llm_response": "",
            "final_response": "",
            "user_id": user_id,
            "session_id": session_id
        }
        
        response = agent.invoke(initial_state)
        final_response = response.get("final_response", "")
        
        return {"result": final_response}
        
    except Exception as e:
        print(f"Error in agent invocation: {e}")
        return {"result": f"<p>Sorry, I encountered an error: {str(e)}</p>"}

if __name__ == "__main__":
    app.run()
