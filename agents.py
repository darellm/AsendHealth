import json
from typing import List, Dict, Any, Callable, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict
import requests
import logging
import os
from langchain.agents import AgentExecutor
from langchain_core.tools import Tool
from langchain.prompts import MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import OllamaLLM
from langchain.chains import LLMChain
from langchain_community.tools import DuckDuckGoSearchRun
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import aiohttp
import asyncio
from urllib.parse import urlparse, quote_plus, parse_qs
from langchain.agents import create_structured_chat_agent
from Bio import Entrez  # For PubMed API (if needed)
from transformers import pipeline  # For summarization
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import re
import time
from selenium.common.exceptions import TimeoutException

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class MedicalTool(BaseModel):
    """Medical tool configuration"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    name: str
    description: str
    function: Callable


class AreyaAgent:
    def __init__(self):
        # Try to initialize the LLM with error handling
        try:
            self.llm = OllamaLLM(
            model="gemma3:4b",
            base_url="http://localhost:11434",
                temperature=0.7,
                streaming=False  # Disable streaming to get the complete response at once
            )
            # Test the LLM connection
            logging.info("Testing Ollama LLM connection...")
            response = requests.get("http://localhost:11434/api/tags")
            if response.status_code != 200:
                logging.warning(
                    f"Ollama server responded with status code {response.status_code}")
            else:
                logging.info("Ollama LLM connection successful")
        except Exception as e:
            logging.error(f"Failed to initialize Ollama LLM: {e}")
            self.llm = None  

        # Configure Chrome to run in proper headless mode
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")  # New headless mode
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")  # Set window size
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-notifications")

        # Initialize the Chrome driver 
        try:
            self.driver = webdriver.Chrome(service=Service(
                ChromeDriverManager().install()), options=chrome_options)
            logging.info("Chrome WebDriver initialized in headless mode")
        except Exception as e:
            logging.error(f"Failed to initialize Chrome WebDriver: {e}")
            # Fallback to simpler initialization if ChromeDriverManager fails
            try:
                self.driver = webdriver.Chrome(options=chrome_options)
                logging.info("Chrome WebDriver initialized with fallback method")
            except Exception as e2:
                logging.error(f"Chrome WebDriver initialization failed completely: {e2}")
                raise

        self.search = DuckDuckGoSearchRun()
        self.conversation_history = []
        self.tools = self._initialize_tools()
        self.prompt = self._create_prompt()

        # IMPORTANT: Initialize session to None, not as an aiohttp.ClientSession()
        # This avoids the "no running event loop" error
        self.session = None

        self.greeting_words = {'hi', 'hello', 'hey', 'greetings',
            'good morning', 'good afternoon', 'good evening'}
        self.current_user = None
        self.last_interaction = None
        self.medical_domains = [
            'pubmed.ncbi.nlm.nih.gov',
            'mayoclinic.org',
            'medlineplus.gov',
            'who.int',
            'nih.gov',
            'cdc.gov',
            'nejm.org',
            'jamanetwork.com'
        ]
        self.medical_sources = {
            'pubmed': 'https://pubmed.ncbi.nlm.nih.gov/?term=',
            'mayoclinic': 'https://www.mayoclinic.org/search/search-results?q=',
            'nih': 'https://www.nih.gov/search?term=',
            'medline': 'https://medlineplus.gov/search?q='
        }

        # Initialize the summarizer
        try:
            # Use CPU explicitly since there are compatibility issues with GPU
            from transformers import pipeline
            # Use PyTorch backend instead of TensorFlow to avoid the XNNPACK delegate error
            self.summarizer = pipeline(
                "summarization",
                model="sshleifer/distilbart-cnn-12-6",
                framework="pt",  # Use PyTorch instead of TensorFlow
                device=-1  # Force CPU usage for better compatibility
            )
            logging.info("Summarization pipeline initialized successfully using PyTorch on CPU")
        except Exception as e:
            logging.error(f"Failed to initialize summarization pipeline: {e}")
            # Create a simple fallback summarizer
            self.summarizer = lambda text, **kwargs: [{"summary_text": text[:500] + "..."}]

    async def __aenter__(self):
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and not self.session.closed:
            await self.session.close()

    # Add method to ensure session is available with better error handling
    async def _ensure_session(self):
        try:
            if self.session is None or self.session.closed:
                logging.info("Creating new aiohttp ClientSession")
                # Create a connector with higher connection limits
                connector = aiohttp.TCPConnector(
                    limit=20,  # Increase from default 100 to avoid connection pool issues
                    limit_per_host=10,  # Allow more connections per host
                    force_close=False,  # Keep connections alive
                    enable_cleanup_closed=True  # Clean up closed connections
                )
                self.session = aiohttp.ClientSession(
                    connector=connector, timeout=aiohttp.ClientTimeout(total=30))
                logging.info("Created new aiohttp session with improved connection settings")
            return self.session
        except RuntimeError as e:
            if "no running event loop" in str(e):
                logging.warning("No running event loop detected, creating new event loop")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # Create a connector with higher connection limits
                connector = aiohttp.TCPConnector(
                    limit=20,
                    limit_per_host=10,
                    force_close=False,
                    enable_cleanup_closed=True
                )
                self.session = aiohttp.ClientSession(
                    connector=connector, timeout=aiohttp.ClientTimeout(total=30))
                logging.info("Created new aiohttp session with event loop recovery")
                return self.session
            else:
                raise

    def set_user_context(self, user_data: Dict[str, Any]):
        """Set the current user context for personalized interactions"""
        self.current_user = user_data
        self.last_interaction = datetime.now()

    def _get_time_appropriate_greeting(self) -> str:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "Good morning"
        elif 12 <= hour < 17:
            return "Good afternoon"
        else:
            return "Good evening"

    def _create_personalized_greeting(self) -> str:
        if not self.current_user:
            return "Hello! I'm Areya, your AI medical assistant."
        name = self.current_user.get('name', 'there')
        time_greeting = self._get_time_appropriate_greeting()
        greeting = f"""[AI Medical Disclaimer]
This information is for educational purposes only.

## Personal Greeting
• {time_greeting}, {name}! Welcome back to your medical assistant.
"""
        if (last_visit := self.current_user.get('last_visit')) and (last_condition := self.current_user.get('last_condition')):
            greeting += f"• On your last visit, we discussed: {last_condition}\n"
            greeting += "• How have you been feeling since then?\n"
        if medical_history := self.current_user.get('medical_history', []):
            greeting += "\n## Quick Health Overview"
            greeting += "\n• I have access to your medical history"
            greeting += "\n• Key conditions: " + ", ".join(medical_history[:3])
        greeting += """\n
## How Can I Help?
• Feel free to ask any medical questions
• I can explain medical terms and conditions
• I can provide general health information
• I can help you understand your medical history

## Important Note
• I maintain strict confidentiality
• For specific medical advice, please consult your healthcare provider"""
        return greeting

    def _create_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are Areya, an advanced medical AI assistant.
YOU MUST FORMAT YOUR RESPONSES EXACTLY AS FOLLOWS:

<response>
[Your complete, well-structured answer using Markdown headings (e.g., ## What is X?) goes here.]
</response>

<research>
[Brief notes, general information, or citations. If none, state "No specific research notes for this query." DO NOT OMIT THIS TAG.]
</research>

Strictly adhere to this format.
"""),
            MessagesPlaceholder(variable_name="chat_history"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
            HumanMessage(content="{input}")
        ])

    def _initialize_tools(self) -> List[Tool]:
        return [
            Tool(
                name="web_search",
                func=self._enhanced_web_search,
                description="Search and analyze medical information from reliable sources"
            ),
            Tool(
                name="medical_database",
                func=self._query_medical_database,
                description="Query internal medical database for conditions and treatments"
            ),
            Tool(
                name="symptom_checker",
                func=self._check_symptoms,
                description="Analyze symptoms and suggest possible conditions"
            )
        ]

    def _query_medical_database(self, query: str) -> str:
        return "Medical database response for: " + query

    def _check_symptoms(self, symptoms: str) -> str:
        return f"Symptom analysis for: {symptoms}"

    def _format_conversation_history(self) -> str:
        formatted = ""
        for message in self.conversation_history[-5:]:
            role = "User" if isinstance(message, HumanMessage) else "Assistant"
            formatted += f"{role}: {message.content}\n"
        return formatted

    async def _scrape_webpage(self, url: str) -> Optional[str]:
        """Scrape a webpage to extract content for medical research."""
        logging.info(f"Scraping webpage: {url}")
        retries = 2
        timeout = 15  # seconds

        for attempt in range(retries):
            try:
                # Set page load timeout for Selenium
                self.driver.set_page_load_timeout(timeout)

                # Navigate to the URL
                await asyncio.to_thread(lambda: self.driver.get(url))

                # Wait for the page to load
                await asyncio.to_thread(lambda: time.sleep(3))

                # Get the page source
                page_source = await asyncio.to_thread(lambda: self.driver.page_source)

                # Parse with BeautifulSoup
                soup = BeautifulSoup(page_source, 'html.parser')

                # Remove unwanted elements
                for element in soup(['script', 'style', 'nav', 'footer', 'iframe', 'noscript', 'svg', 'header']):
                    element.decompose()

                # Remove elements that are likely advertisements or menus
                for element in soup.find_all(class_=lambda c: c and any(x in str(c).lower() for x in ['ad', 'banner', 'menu', 'nav', 'sidebar', 'footer', 'cookie', 'popup'])):
                    element.decompose()

                # Common content selectors in medical websites
                content_selectors = [
                    'article', 'main', '.content', '#content', '.article', '.post-content', '.entry-content',
                    '.main-content', '#main-content', '.article-content', '.page-content', '.post-body',
                    '.abstract', '.summary', '#maincontent', '.maincontent', '[role="main"]',
                    '.mw-parser-output'  # For Wikipedia
                ]

                # Try to find the main content area
                main_content = None
                for selector in content_selectors:
                    main_content = soup.select_one(selector)
                    if main_content:
                        logging.info(f"Found main content using selector: {selector}")
                    break

                if main_content:
                    # Extract text from the main content
                    content = main_content.get_text(separator=' ', strip=True)
                else:
                    # If no main content area found, extract from body
                    logging.info("No main content area found, extracting from body")
                    body = soup.body
                    if not body:
                        return None

                    # Get all paragraphs and headings
                    paragraphs = body.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'])

                    # Extract text from each element
                    content_parts = []
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if text and len(text) > 20:  # Only include non-trivial text
                            content_parts.append(text)

                    if not content_parts:
                        # If no paragraphs found, fall back to all text
                        content = body.get_text(separator=' ', strip=True)
                    else:
                        content = ' '.join(content_parts)

                # Clean up the content
                # Replace multiple spaces with a single space
                content = re.sub(r'\s+', ' ', content)
                # Replace newlines, tabs with spaces
                content = re.sub(r'[\n\r\t]', ' ', content)

                # Check if content is meaningful
                if not content or len(content) < 100:
                    if attempt < retries - 1:
                        logging.warning(f"Insufficient content extracted, retrying ({attempt + 1}/{retries})")
                        # Wait before retrying
                        await asyncio.to_thread(lambda: time.sleep(2))
                        continue
                    else:
                        logging.warning("Failed to extract meaningful content after retries")
                        return None

                # Truncate very long content to a reasonable size
                if len(content) > 20000:
                    content = content[:20000]
                    logging.info("Content truncated due to excessive length")

                # Log success
                logging.info(f"Successfully scraped content from {url} ({len(content)} chars)")
                return content
            except Exception as e:
                logging.error(f"Error scraping {url} (attempt {attempt + 1}/{retries}): {str(e)}")
                if attempt < retries - 1:
                    # Wait before retrying
                    await asyncio.to_thread(lambda: time.sleep(2))
                else:
                    return None

        return None

    async def _enhanced_web_search(self, query: str) -> str:
        """Perform a web search and return formatted research/search results for UI"""
        try:
            logging.info(f"Starting enhanced web search for query: {query}")
            
            # Making  the search query more specific for medical information
            medical_query = f"medical information about {query}"
            
            # Use the search engine API to get better results
            search_results = []
            
            try:
                # First trying DuckDuckGo search
                search_results = await self.perform_duckduckgo_search(medical_query)
                logging.info(f"DuckDuckGo search returned {len(search_results)} results")
                
                # Explicitly add medical sources regardless of search results
                medical_sources = [
                    f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}",
                    f"https://www.mayoclinic.org/search/search-results?q={quote_plus(query)}",
                    f"https://medlineplus.gov/search?query={quote_plus(query)}",
                    f"https://www.nih.gov/search?term={quote_plus(query)}",
                    f"https://www.cdc.gov/search/?query={quote_plus(query)}",
                    f"https://www.google.com/search?q={quote_plus('medical information ' + query)}"
                ]
                
                # Adding medical sources to the start of the search results
                for source in medical_sources:
                    if source not in search_results:
                        search_results.insert(0, source)
                
                logging.info(f"After adding medical sources, total results: {len(search_results)}")
                
            except Exception as search_error:
                logging.error(f"Error during search: {search_error}")
                # Provide medical sources as a fallback
                search_results = [
                    f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}",
                    f"https://www.mayoclinic.org/search/search-results?q={quote_plus(query)}",
                    f"https://medlineplus.gov/search?query={quote_plus(query)}",
                    f"https://www.nih.gov/search?term={quote_plus(query)}",
                    f"https://www.webmd.com/search/search_results/default.aspx?query={quote_plus(query)}",
                    f"https://www.google.com/search?q={quote_plus('medical information ' + query)}"
                ]
                logging.info(f"Using fallback medical sources: {len(search_results)} sources")

            # Actually scrape content from each source
            scraped_contents = {}
            
            # Limit to 4 sources to avoid overloading
            for url in search_results[:4]:
                try:
                    content = await self._scrape_webpage(url)
                    if content and len(content) > 200:  # Only use content that has reasonable length
                        # Get domain for identification
                        domain = url.split("//")[1].split("/")[0]
                        if "www." in domain:
                            domain = domain.split("www.")[1]
                        
                        # Summarize the content if it's too long
                        if len(content) > 1000:
                            summary = self._summarize_text(content)
                            scraped_contents[domain] = {
                                "url": url,
                                "content": content[:300] + "...",  # Preview
                                "summary": summary
                            }
                        else:
                            scraped_contents[domain] = {
                                "url": url,
                                "content": content,
                                "summary": content[:200] + "..."
                            }
                        
                        logging.info(f"Successfully scraped content from {domain} ({len(content)} chars)")
                except Exception as scrape_error:
                    logging.error(f"Error scraping {url}: {str(scrape_error)}")
                
            # Format results for research display
            formatted_results = []
            source_id = 0
            
            # Process each URL and create HTML for it
            for url in search_results[:6]:  # Limit to 6 sources
                try:
                    source_id += 1
                    domain = url.split("//")[1].split("/")[0]
                    if "www." in domain:
                        domain = domain.split("www.")[1]
                    
                    # Determine source name based on domain
                    source_name = domain
                    if "pubmed" in domain or "ncbi.nlm.nih.gov" in domain:
                        source_name = "PubMed (National Library of Medicine)"
                    elif "mayoclinic" in domain:
                        source_name = "Mayo Clinic"
                    elif "medlineplus" in domain:
                        source_name = "MedlinePlus (NIH)"
                    elif "nih.gov" in domain:
                        source_name = "National Institutes of Health"
                    elif "webmd" in domain:
                        source_name = "WebMD"
                    elif "healthline" in domain:
                        source_name = "Healthline"
                    elif "cdc.gov" in domain:
                        source_name = "Centers for Disease Control and Prevention"
                    elif "who.int" in domain:
                        source_name = "World Health Organization"
                    elif "google.com" in domain:
                        source_name = "Google Search Results"
                    
                    # Create a unique source ID for this source
                    sourceId = f"source-{source_id}"
                    
                    # Get scraped content if available
                    scraped_content_html = ""
                    if domain in scraped_contents:
                        scraped_data = scraped_contents[domain]
                        scraped_content_html = f"""
                        <div class="scraped-content">
                            <h5>Content Summary:</h5>
                            <p class="content-summary">{scraped_data.get('summary', 'No summary available')}</p>
                            <div class="full-content" style="display: none;">
                                <h5>Full Content:</h5>
                                <div class="scrollable-content">{scraped_data.get('content', 'No content available')}</div>
                            </div>
                            <button class="toggle-full-content" onclick="toggleFullContent(this)">Show Full Content</button>
                        </div>
                        """
                    
                    # Create HTML for this source
                    source_html = f"""
                    <div class="research-source" id="container-{sourceId}" data-url="{url}">
                        <div class="source-header">
                            <i class="fas fa-external-link-alt"></i>
                            <div class="source-domain">{domain}</div>
                        </div>
                        <div class="source-content">
                            <h4>{source_name}</h4>
                            <p>This resource provides medical information about {query}, including potential symptoms, causes, treatments, and other health details.</p>
                            {scraped_content_html}
                        </div>
                        <div class="source-actions">
                            <button class="preview-button" onclick="toggleSourcePreview(document.getElementById('container-{sourceId}'))">
                                <i class="fas fa-eye"></i> Preview Source
                            </button>
                            <a href="{url}" target="_blank" class="external-link">
                                <i class="fas fa-external-link-alt"></i> Visit Source
                            </a>
                        </div>
                        <div class="source-preview">
                            <div class="iframe-container">
                                <iframe src="{url}" title="{source_name}" loading="lazy" sandbox="allow-scripts allow-same-origin"></iframe>
                            </div>
                        </div>
                    </div>
                    """
                    formatted_results.append(source_html)
                    logging.info(f"Added source to research panel: {source_name} ({domain})")
                        
                except Exception as format_error:
                    logging.error(f"Error formatting search result: {format_error}")
                    
            # If we couldn't get any results, provide a fallback
            if not formatted_results:
                logging.warning("No formatted results generated, using fallback sources")
                source_id = 0
                fallback_sources = [
                    {"url": f"https://www.mayoclinic.org/search/search-results?q={quote_plus(query)}", "name": "Mayo Clinic"},
                    {"url": f"https://medlineplus.gov/search?query={quote_plus(query)}", "name": "MedlinePlus (NIH)"},
                    {"url": f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}", "name": "PubMed"},
                    {"url": f"https://www.google.com/search?q={quote_plus('medical ' + query)}", "name": "Google Search"}
                ]
                
                for source in fallback_sources:
                    source_id += 1
                    sourceId = f"source-{source_id}"
                    domain = source["url"].split("//")[1].split("/")[0]
                    if "www." in domain:
                        domain = domain.split("www.")[1]
                        
                    source_html = f"""
                    <div class="research-source" id="container-{sourceId}" data-url="{source["url"]}">
                        <div class="source-header">
                            <i class="fas fa-external-link-alt"></i>
                            <div class="source-domain">{domain}</div>
                        </div>
                        <div class="source-content">
                            <h4>{source["name"]}</h4>
                            <p>This resource may provide reliable medical information about {query}.</p>
                        </div>
                        <div class="source-actions">
                            <button class="preview-button" onclick="toggleSourcePreview(document.getElementById('container-{sourceId}'))">
                                <i class="fas fa-eye"></i> Preview Source
                            </button>
                            <a href="{source["url"]}" target="_blank" class="external-link">
                                <i class="fas fa-external-link-alt"></i> Visit Source
                            </a>
                        </div>
                        <div class="source-preview">
                            <div class="iframe-container">
                                <iframe src="{source["url"]}" title="{source["name"]}" loading="lazy" sandbox="allow-scripts allow-same-origin"></iframe>
                            </div>
                        </div>
                    </div>
                    """
                    formatted_results.append(source_html)
            
            # Log the number of sources that will be displayed
            logging.info(f"Total formatted medical sources: {len(formatted_results)}")
                
            # Add medical disclaimer
            medical_disclaimer = """
            <div class="medical-disclaimer">
                <h3>Medical Information Disclaimer</h3>
                <p>The information provided here is for educational purposes only and not a substitute for professional medical advice. 
                Always consult with a qualified healthcare provider for medical concerns.</p>
            </div>
            """
            
            # Create JavaScript for toggling full content
            toggle_content_script = """
            <script>
            function toggleFullContent(button) {
                const contentDiv = button.previousElementSibling;
                if (contentDiv.style.display === "none" || !contentDiv.style.display) {
                    contentDiv.style.display = "block";
                    button.textContent = "Hide Full Content";
                } else {
                    contentDiv.style.display = "none";
                    button.textContent = "Show Full Content";
                }
            }
            </script>
            """
            
            # Create JavaScript function for toggling previews
            toggle_script = """
            <script>
            function toggleSourcePreview(sourceId) {
                if (sourceId instanceof HTMLElement) {
                    const sourceElement = sourceId;
                    const previewElement = sourceElement.querySelector('.source-preview');
                    if (previewElement) {
                        previewElement.classList.toggle('active');
                        
                        const button = sourceElement.querySelector('.preview-button');
                        if (button) {
                            if (previewElement.classList.contains('active')) {
                                button.innerHTML = '<i class="fas fa-eye-slash"></i> Hide Preview';
                                
                                const iframe = previewElement.querySelector('iframe');
                                if (iframe && !iframe.src) {
                                    const url = sourceElement.getAttribute('data-url');
                                    if (url) iframe.src = url;
                                }
                            } else {
                                button.innerHTML = '<i class="fas fa-eye"></i> Preview Source';
                            }
                        }
                    }
                }
            }
            </script>
            """
            
            # Combine all elements
            research_html = f"""
            <h2>Medical Research Sources for "{query}"</h2>
            <p>Below are medical sources with web-scraped content about "<strong>{query}</strong>":</p>
            <div class="sources-container">
                {''.join(formatted_results)}
            </div>
            {medical_disclaimer}
            {toggle_content_script}
            {toggle_script}
            """
            
            logging.info(f"Returning formatted research content with {len(formatted_results)} sources")
            return research_html
            
        except Exception as e:
            logging.error(f"Error in enhanced web search: {e}")
            
            # Return a simplified fallback with generic medical sources
            fallback_html = f"""
            <h2>Medical Resources</h2>
            <p>Here are some reliable medical resources for information about "{query}":</p>
            
            <div class="research-source" id="fallback-source-1" data-url="https://www.mayoclinic.org/search/search-results?q={quote_plus(query)}">
                <div class="source-header">
                    <i class="fas fa-external-link-alt"></i>
                    <div class="source-domain">mayoclinic.org</div>
                </div>
                <div class="source-content">
                    <h4>Mayo Clinic</h4>
                    <p>The Mayo Clinic offers comprehensive information about various medical conditions.</p>
                </div>
                <div class="source-actions">
                    <button class="preview-button" onclick="toggleSourcePreview(document.getElementById('fallback-source-1'))">
                        <i class="fas fa-eye"></i> Preview Source
                    </button>
                    <a href="https://www.mayoclinic.org/search/search-results?q={quote_plus(query)}" target="_blank" class="external-link">
                        <i class="fas fa-external-link-alt"></i> Visit Source
                    </a>
                </div>
                <div class="source-preview">
                    <div class="iframe-container">
                        <iframe loading="lazy" sandbox="allow-scripts allow-same-origin"></iframe>
                    </div>
                </div>
            </div>
            
            <div class="research-source" id="fallback-source-2" data-url="https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}">
                <div class="source-header">
                    <i class="fas fa-external-link-alt"></i>
                    <div class="source-domain">pubmed.ncbi.nlm.nih.gov</div>
                </div>
                <div class="source-content">
                    <h4>PubMed</h4>
                    <p>PubMed provides access to scientific research and medical literature from the National Library of Medicine.</p>
                </div>
                <div class="source-actions">
                    <button class="preview-button" onclick="toggleSourcePreview(document.getElementById('fallback-source-2'))">
                        <i class="fas fa-eye"></i> Preview Source
                    </button>
                    <a href="https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}" target="_blank" class="external-link">
                        <i class="fas fa-external-link-alt"></i> Visit Source
                    </a>
                </div>
                <div class="source-preview">
                    <div class="iframe-container">
                        <iframe loading="lazy" sandbox="allow-scripts allow-same-origin"></iframe>
                    </div>
                </div>
            </div>
            
            <div class="research-source" id="fallback-source-3" data-url="https://www.cdc.gov/search/?query={quote_plus(query)}">
                <div class="source-header">
                    <i class="fas fa-external-link-alt"></i>
                    <div class="source-domain">cdc.gov</div>
                </div>
                <div class="source-content">
                    <h4>Centers for Disease Control and Prevention</h4>
                    <p>The CDC provides trusted information about diseases, treatments, and health guidance.</p>
                </div>
                <div class="source-actions">
                    <button class="preview-button" onclick="toggleSourcePreview(document.getElementById('fallback-source-3'))">
                        <i class="fas fa-eye"></i> Preview Source
                    </button>
                    <a href="https://www.cdc.gov/search/?query={quote_plus(query)}" target="_blank" class="external-link">
                        <i class="fas fa-external-link-alt"></i> Visit Source
                    </a>
                </div>
                <div class="source-preview">
                    <div class="iframe-container">
                        <iframe loading="lazy" sandbox="allow-scripts allow-same-origin"></iframe>
                    </div>
                </div>
            </div>
            
            <div class="research-source" id="fallback-source-4" data-url="https://www.google.com/search?q={quote_plus('medical ' + query)}">
                <div class="source-header">
                    <i class="fas fa-external-link-alt"></i>
                    <div class="source-domain">google.com</div>
                </div>
                <div class="source-content">
                    <h4>Google Search Results</h4>
                    <p>Google search results for medical information about {query}.</p>
                </div>
                <div class="source-actions">
                    <button class="preview-button" onclick="toggleSourcePreview(document.getElementById('fallback-source-4'))">
                        <i class="fas fa-eye"></i> Preview Source
                    </button>
                    <a href="https://www.google.com/search?q={quote_plus('medical ' + query)}" target="_blank" class="external-link">
                        <i class="fas fa-external-link-alt"></i> Visit Source
                    </a>
                </div>
                <div class="source-preview">
                    <div class="iframe-container">
                        <iframe loading="lazy" sandbox="allow-scripts allow-same-origin"></iframe>
                    </div>
                </div>
            </div>
            
            <div class="medical-disclaimer">
                <h3>Medical Information Disclaimer</h3>
                <p>The information provided here is for educational purposes only and not a substitute for professional medical advice. 
                Always consult with a qualified healthcare provider for medical concerns.</p>
            </div>
            """
            
            logging.info("Using fallback HTML for research due to error")
            return fallback_html

    def _extract_urls(self, search_results: str) -> List[str]:
        urls = []
        for line in search_results.split('\n'):
            if 'http' in line:
                start = line.find('http')
                end = line.find(' ', start) if ' ' in line[start:] else len(line)
                url = line[start:end].strip()
                if url and len(url) > 10:
                    urls.append(url)
        return urls

    def _extract_key_points(self, content: str, max_points: int = 3) -> str:
        if not content:
            return "• Information not available\n"
        sentences = content.split('.')
        key_points = []
        for sentence in sentences:
            sentence = sentence.strip()
            if (len(sentence) > 20 and 
                any(term in sentence.lower() for term in ['treatment', 'therapy', 'research', 'study', 'clinical', 'patient', 'effect', 'medicine', 'result', 'trial', 'evidence']) and
                not any(skip in sentence.lower() for skip in ['cookie', 'privacy', 'advertisement', 'subscribe'])):
                key_points.append(f"• {sentence}.")
                if len(key_points) >= max_points:
                    break
        return '\n'.join(key_points) if key_points else "• No relevant information found\n"

    def _summarize_text(self, text: str) -> str:
        try:
            if len(text) < 50:
                return text
            summary = self.summarizer(text, max_length=150, min_length=30, do_sample=False)[0]["summary_text"]
            return summary
        except Exception as e:
            logging.error(f"Error summarizing text: {e}")
            return "Summary not available."

    async def process_message(self, user_input: str, patient_context: Dict[str, Any] = None, deep_research_mode: bool = False, show_thinking: bool = False) -> str:
        try:
            # Initialize default timeout value
            llm_timeout = 90  # Default timeout of 90 seconds for all queries

            # Clean up user input - remove trailing slashes and trim whitespace
            user_input = user_input.rstrip('/').strip()

            if patient_context:
                self.set_user_context(patient_context)
            
            # Simple greeting detection and response
            if any(word.lower() in user_input.lower() for word in self.greeting_words):
                greeting = self._create_personalized_greeting()
                return f"{greeting}\\n|||\\n<h3>No Research Needed</h3>"

            current_temperature = 0.7
            # For standard medical queries in simple mode, use a clearer prompt template
            if not deep_research_mode:
                current_temperature = 0.4 # Lower temperature for more focused normal mode
                prompt = (
                    "You are Areya, a medical AI assistant. "
                    f"The user asked: '{user_input}'\n\n"
                    "Please provide a clear, concise, and well-structured explanation. "
                    "Use Markdown for formatting. Your response should include:\n"
                    "- A main title (e.g., using ##).\n"
                    "- Sub-headings for key sections (e.g., Definition, Symptoms, Causes, Treatment using ###).\n"
                    "- **Bold text** for important keywords and terms.\n"
                    "- Bulleted lists for items like symptoms or treatment options.\n"
                    "- Horizontal rules (---) to visually separate major sections if appropriate.\n"
                    "Ensure the information is accurate and easy to understand.\n\n"
                    "FORMAT YOUR RESPONSE STRICTLY AS FOLLOWS (within the <response> tags):\n\n"
                    "<response>\n"
                    "## [Main Title for the Topic]\n\n"
                    "**[Section Sub-Heading e.g., Definition]**\n\n"
                    "[Detailed paragraph for this section. Use **bolding** for key terms.]\n\n"
                    "---\n\n"
                    "### [Next Section Sub-Heading e.g., Symptoms]\n\n"
                    "*   [Symptom 1 or Point 1]\n"
                    "*   [Symptom 2 or Point 2]\n"
                    "    *   [Nested point if applicable]\n\n"
                    "[Further explanation for this section if needed.]\n\n"
                    "---\n"
                    "[Continue with other sections as appropriate, following this structure.]\n\n"
                    "### Important Note\n\n"
                    "[Any crucial disclaimers or important points.]\n"
                    "</response>\n\n"
                    "<research>\n"
                    "[Brief note, e.g., 'General medical information compiled from standard knowledge.']\n"
                    "</research>\n\n"
                    "ADHERE TO THIS FORMAT EXACTLY."
                )
            else:
                # In deep research mode, provide comprehensive information with citations
                prompt = (
                    "You are Areya, a medical AI assistant providing exhaustive medical information. "
                    f"User asked: '{user_input}'\\n\\n"
                    "Your response must be EXTREMELY DETAILED (800-1000 words), using Markdown headings for sections like: "
                    "## Definition, ## Epidemiology, ## Pathophysiology, ## Causes, ## Symptoms, ## Diagnosis, ## Treatment, ## Management, ## Prognosis, ## Prevention, ## Research Directions.\\n\\n"
                    "FORMAT YOUR RESPONSE STRICTLY AS FOLLOWS:\\n\\n"
                    "<response>\\n"
                    "[Your comprehensive explanation with Markdown headings.]\\n"
                    "</response>\\n\\n"
                    "<research>\\n"
                    "[Note on research approach, e.g., 'Information compiled from established medical knowledge.']\\n"
                    "</research>\\n\\n"
                    "ADHERE TO THIS FORMAT EXACTLY."
                )

            # Make direct API call to Ollama
            try:
                headers = {"Content-Type": "application/json"}
                current_num_predict = 3000 # Default for deep research
                if not deep_research_mode:
                    current_num_predict = 1024 # Reduced for normal mode for speed

                request_data = {
                    "model": "gemma3:4b",
                    "prompt": prompt,
                    "stream": False,
                    "temperature": current_temperature, 
                    "raw": False,  # Changed from True to False
                    "num_predict": current_num_predict
                }
                
                logging.info(f"Making direct API call to Ollama. Mode: {'Deep Research' if deep_research_mode else 'Normal'}. Num_predict: {current_num_predict}, Temp: {current_temperature}, Raw: False")
                api_response = requests.post(
                    "http://localhost:11434/api/generate",
                    headers=headers,
                    json=request_data,
                    timeout=llm_timeout
                )
                api_response.raise_for_status()
                response_data = api_response.json()
                
                # Extract the response content - adjusted for raw: False
                # When raw is False, the response is typically in response_data['response'] for /api/generate
                # or response_data['message']['content'] for /api/chat if that endpoint structure was used.
                # Sticking to /api/generate, 'response' key should hold the string.
                response_text = response_data.get("response", "").strip()
                
                logging.info(f"Raw LLM Output (first 200 chars): {response_text[:200]}")

                # More flexible regex for extracting response and research sections
                response_match = re.search(r'<\s*response\s*>([\s\S]*?)<\s*/\s*response\s*>', response_text, re.DOTALL | re.IGNORECASE)
                research_match = re.search(r'<\s*research\s*>([\s\S]*?)<\s*/\s*research\s*>', response_text, re.DOTALL | re.IGNORECASE)
                
                final_response = ""
                research_content = ""

                if response_match:
                    final_response = response_match.group(1).strip()
                    logging.info("Successfully extracted content from <response> tags.")
                else:
                    logging.warning("Could not find <response> tags. Using full response_text as final_response.")
                    # Fallback: if no <response> tag, check if the whole text seems like a plausible response
                    # and doesn't contain <research> tags within it confusingly.
                    if not research_match or research_match.start() > len(response_text) * 0.8: # if research is very late or not there
                        final_response = response_text 
                    else: # response_text likely contains research tag, try to split
                        final_response = response_text.split("<research>")[0].strip() if "<research>" in response_text.lower() else response_text


                if research_match:
                    research_content = research_match.group(1).strip()
                    logging.info("Successfully extracted content from <research> tags.")
                else:
                    logging.warning("Could not find <research> tags.")
                    # If response_match was found but research_match wasn't, try to get text after response
                    if response_match and response_match.end() < len(response_text):
                         potential_research = response_text[response_match.end():].strip()
                         if potential_research.lower().startswith("<research>") and potential_research.lower().endswith("</research>"): # Should have been caught by regex
                             pass # Regex should have caught this
                         elif len(potential_research) > 5: # Some arbitrary content left
                             research_content = "Note: Could not reliably parse research section. Content found after response block: " + potential_research[:100] + "..."
                         else:
                             research_content = "No specific research notes provided."
                    elif not final_response and response_text: # No tags found at all
                         research_content = "Research section not identified."
                    else:
                         research_content = "No specific research notes provided."


                # Ensure we have a valid response, even after fallback
                if not final_response or len(final_response.strip()) < 20:
                    if response_text and len(response_text.strip()) > 20 and not response_match and not research_match :
                        # If no tags were found at all, and raw response_text is substantial, use it as final_response
                        logging.info("No tags found, using full response_text as final_response as it seems substantial.")
                        final_response = response_text
                        research_content = "Research section not identified; full output treated as response."
                    else:
                        logging.warning("Final response is too short or empty after parsing. Generating fallback.")
                        final_response = self._generate_fallback_response(user_input).replace("<response>","").replace("</response>","") # Use internal fallback
                        research_content = "Default fallback response generated."
                
                # For deep research mode, we'll perform an actual web search and replace research_content
                if deep_research_mode:
                    try:
                        logging.info("Deep research mode activated, performing web search")
                        research_html = await self._enhanced_web_search(user_input)
                        logging.info(f"Web search results retrieved: {len(research_html)} characters")
                        complete_response = f"{final_response}|||{research_html}"
                    except Exception as search_error:
                        logging.error(f"Error in deep research mode: {search_error}")
                        complete_response = f"{final_response}|||{research_content}" # Use LLM's research if web search fails
                else:
                    # Ensure research_content has some value for normal mode
                    if not research_content.strip():
                        research_content = "Standard medical information presented."
                    complete_response = f"{final_response}|||<h3>Simple Mode Context</h3><p>{research_content}</p>"
                
                return complete_response
                
            except requests.exceptions.RequestException as e:
                logging.error(f"Error calling Ollama API: {e}")
                error_response = (
                    "<response>\n"
                    "I apologize, but I'm having trouble processing your request at the moment. "
                    "Please try again in a few moments.\n"
                    "</response>\n"
                    "|||"
                    "<h3>Error Details</h3>"
                    f"<p>Error: {str(e)}</p>"
                )
                return error_response
                
        except Exception as e:
            logging.error(f"Error in process_message: {e}")
            return f"<response>An error occurred: {str(e)}</response>|||<h3>Error</h3><p>{str(e)}</p>"

    def _generate_fallback_response(self, user_input: str) -> str:
        """Generate a helpful fallback response when the model fails to provide a good answer."""
        try:
            # Simplify the user query to extract the key term
            cleaned_query = user_input.lower().strip().rstrip('?').strip()
            # Remove common question prefixes
            for prefix in ["what is", "define", "explain", "tell me about"]:
                if cleaned_query.startswith(prefix):
                    cleaned_query = cleaned_query[len(prefix):].strip()
            
            # Make a final desperate attempt to directly get a definition
            try:
                logging.info(f"Making emergency fallback definition attempt for: '{cleaned_query}'")
                emergency_prompt = (
                    f"Define the term '{cleaned_query}' in medical context with a comprehensive explanation (at least 150 words). "
                    f"Include what it is, causes, symptoms, and significance. "
                    f"Your response must be in the format: <response>Your detailed explanation here</response>"
                )
                
                emergency_response = requests.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": "gemma3:4b",
                        "messages": [
                            {
                                "role": "system", 
                                "content": "You are a medical AI assistant who answers health-related questions with accurate information."
                            },
                            {
                                "role": "user",
                                "content": emergency_prompt
                            }
                        ],
                        "options": {
                            "num_predict": 6000,
                            "temperature": 0.1,
                            "seed": 123
                        }
                    },
                    timeout=30  # Quick timeout for emergency attempt
                )
                
                if emergency_response.status_code == 200:
                    try:
                        # Handle streaming JSON responses by capturing the full content
                        emergency_response_text = emergency_response.text
                        # Each line is a separate JSON object in the streaming response
                        lines = [line.strip() for line in emergency_response_text.split('\n') if line.strip()]
                        
                        emergency_result = ""
                        for line in lines:
                            try:
                                line_json = json.loads(line)
                                if "message" in line_json and "content" in line_json["message"]:
                                    emergency_result += line_json["message"]["content"]
                            except json.JSONDecodeError:
                                logging.warning(f"Failed to parse emergency JSON line: {line[:50]}...")
                        
                        logging.info(f"Assembled emergency streaming response: {len(emergency_result)} chars")
                        
                        if emergency_result and len(emergency_result.strip()) > 100:
                            # Check if response has tags
                            response_match = re.search(r'<response>(.*?)</response>', emergency_result, re.DOTALL)
                            if response_match:
                                logging.info("Emergency definition successful")
                                return f"<response>{response_match.group(1).strip()}</response>"
                            elif len(emergency_result.strip()) > 150:
                                logging.info("Using untagged emergency result")
                                return f"<response>{emergency_result}</response>"
                    except Exception as json_error:
                        logging.error(f"Error parsing emergency JSON response: {json_error}")
                        emergency_result = emergency_response.text
                        # Try to extract content if it has the correct format
                        if "<response>" in emergency_result and "</response>" in emergency_result:
                            start = emergency_result.find("<response>") + len("<response>")
                            end = emergency_result.find("</response>")
                            emergency_result = emergency_result[start:end].strip()
                            logging.info(f"Extracted emergency response from text: {len(emergency_result)} chars")
                            return f"<response>{emergency_result}</response>"
            except Exception as e:
                logging.error(f"Emergency definition failed: {e}")
            
            # If all else fails, use the generic fallback
            return f"""<response>
I apologize, but I wasn't able to provide a complete answer about '{cleaned_query}' at this moment.

To get better information about this medical topic, you could:
• Try enabling Deep Research Mode for more comprehensive results
• Ask a more specific question about what aspects of {cleaned_query} interest you
• Request information about causes, symptoms, treatments, or risk factors
• Consider consulting reliable medical resources for detailed information

I'm designed to provide medical information dynamically, but sometimes need more context or your query may need rephrasing for me to give you the best possible answer.
</response>"""
        except Exception as e:
            logging.error(f"Error generating fallback response: {e}")
            return """<response>I apologize, but I'm unable to provide a complete answer at this moment. Please try rephrasing your question or try again later.</response>"""

    # Add DuckDuckGo search function
    async def perform_duckduckgo_search(self, query: str) -> List[str]:
        """Perform a DuckDuckGo search and return a list of URLs"""
        search_urls = []
        ddg_query = f"{query} medical health"
        
        try:
            # Encode the search query
            encoded_query = quote_plus(ddg_query)
            ddg_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
            
            logging.info(f"Searching DuckDuckGo with query: {ddg_query}")
            
            # Create a simple browser-like headers to avoid being blocked
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://duckduckgo.com/',
                'DNT': '1',  # Do Not Track
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Use aiohttp for the request
            async with self.session.get(ddg_url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    html_content = await response.text()
                    
                    # Parse the HTML with BeautifulSoup
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Extract result links - DuckDuckGo HTML results have different structure than Google
                    result_elements = soup.select('.result__a') or soup.select('.result-link')
                    
                    # Alternative selectors if the primary ones don't work
                    if not result_elements:
                        logging.info("Using alternative DuckDuckGo selectors")
                        result_elements = soup.select('a.result__url') or soup.select('a[href^="http"]')
                    
                    # Process found elements
                    seen_urls = set()
                    for element in result_elements:
                        try:
                            # Get the href attribute
                            url = element.get('href')
                            
                            # DuckDuckGo sometimes uses redirects, extract the actual URL
                            if url and '/redirect/' in url:
                                parsed = urlparse(url)
                                query_params = parse_qs(parsed.query)
                                if 'uddg' in query_params:
                                    url = query_params['uddg'][0]
                                
                            # Filter valid URLs
                            if (url and 
                                url.startswith('http') and 
                                'duckduckgo.com' not in url and
                                url not in seen_urls and
                                not any(ad_term in url.lower() for ad_term in ['ad.', 'ads.', 'advertisement'])):
                                
                                # Prioritize medical websites
                                medical_domains = ['nih.gov', 'mayoclinic.org', 'who.int', 'healthline.com', 
                                                  'webmd.com', 'medlineplus.gov', 'cdc.gov', 'health.harvard.edu']
                                
                                is_medical = any(domain in url.lower() for domain in medical_domains)
                                
                                # Add medical sites first, then others
                                if is_medical or len(search_urls) < 5:
                                    search_urls.append(url)
                                    seen_urls.add(url)
                                    logging.info(f"Found DuckDuckGo URL: {url}")
                                    
                                    # Stop once we have enough results
                                    if len(search_urls) >= 8:
                                        break
                        except Exception as e:
                            logging.error(f"Error extracting DuckDuckGo URL: {str(e)}")
                            continue
                    
                    logging.info(f"Found {len(search_urls)} URLs from DuckDuckGo")
                else:
                    logging.error(f"DuckDuckGo returned status code: {response.status}")
        except Exception as e:
            logging.error(f"DuckDuckGo search error: {str(e)}")
    
        return search_urls

    def _generate_error_response(self, message: str) -> str:
        """Generate a formatted error response"""
        return f"""[AI Medical Disclaimer]
This information is for educational purposes only.

## Error Notice
• {message}

## Next Steps
• Consult with your healthcare provider.
• Contact support if the issue persists."""

def ask_medical_chatbot_sync(user_query: str, point_id: str, deep_research_mode: bool = False, patient_context: Optional[Dict[str, Any]] = None) -> str:
    """Synchronous wrapper for ask_medical_chatbot"""
    agent = AreyaAgent()
    return asyncio.run(agent.process_message(user_query, patient_context, deep_research_mode))

# if __name__ == "__main__":
#     print(ask_medical_chatbot_sync("what is a stroke ?",None,False,None))