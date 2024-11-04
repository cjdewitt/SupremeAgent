import threading
import time
from typing import List, Tuple, Dict, Any, Optional, Callable
from dataclasses import dataclass
import logging
import os
import subprocess
import tempfile
import sys
from urllib.parse import quote_plus
from swarm import Swarm, Agent
from openai import OpenAI 
import pyautogui
import platform
import base64
from io import BytesIO
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG to capture all levels of log messages
    format='%(asctime)s - %(levelname)s - %(message)s',  
    handlers=[
        logging.FileHandler("supreme_agent.log"),  # Log to a file
        logging.StreamHandler()  # Also log to console
    ]
)

@dataclass
class AgentConfig:
    """Configuration for an individual agent."""
    name: str
    instructions: str
    tools: List[str]
    next_agent: Optional[str] = None

class TranslationProgress:
    """Progress indicator for long-running operations."""
    def __init__(self):
        self._stop = False
        self._thread = None

    def start(self):
        self._stop = False
        self._thread = threading.Thread(target=self._progress_indicator)
        self._thread.start()

    def stop(self):
        self._stop = True
        if self._thread:
            self._thread.join()

    def _progress_indicator(self):
        stages = ["Processing", "Analyzing", "Generating response"]
        current_stage = 0
        while not self._stop:
            print(f"\r{stages[current_stage]} {'.' * (current_stage + 1)}", end='', flush=True)
            time.sleep(0.5)
            current_stage = (current_stage + 1) % len(stages)

@dataclass
class SystemResources:
    """Manages system resources like browser, editor, and terminal."""
    def __init__(self):
        self.browser: Optional[webdriver.Chrome] = None
        self.editor: Optional[str] = None
        self.terminal: Optional[str] = None
        self.working_directory = tempfile.mkdtemp()
        os.chdir(self.working_directory)
        logging.info(f"Changed working directory to {self.working_directory}")
        self.os_type = platform.system()

    def browser_search(self, query: str) -> str:
        """Search Google with Selenium and retrieve the first search result."""
        try:
            driver = self.setup_webdriver()
            if driver is None:
                return "Failed to initialize WebDriver"

            # Perform Google Search
            search_url = f"https://www.google.com/search?q={quote_plus(query)}"
            driver.get(search_url)
            logging.info(f"Navigated to {search_url}")

            # Wait for the results to load using WebDriverWait
            wait = WebDriverWait(driver, 10)
            first_result = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div#search div.g')))

            # Retrieve the first search result
            title = first_result.find_element(By.TAG_NAME, 'h3').text
            link = first_result.find_element(By.TAG_NAME, 'a').get_attribute('href')

            result = f"Title: {title}\nURL: {link}"
            logging.info(f"First search result retrieved: {result}")

            return result
        except Exception as e:
            logging.error(f"Browser search error: {e}")
            return f"Browser search error: {str(e)}"

    def setup_webdriver(self) -> Optional[webdriver.Chrome]:
        """Initializes the Selenium WebDriver."""
        if self.browser is not None:
            logging.info("WebDriver already initialized")
            return self.browser

        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Run in headless mode
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")

            # Initialize WebDriver
            service = Service()  
            driver = webdriver.Chrome(service=service, options=chrome_options)
            self.browser = driver
            logging.info("Selenium WebDriver initialized successfully")
            return self.browser
        except Exception as e:
            logging.error(f"Failed to initialize WebDriver: {e}")
            return None

    def close_webdriver(self):
        """Closes the Selenium WebDriver."""
        if self.browser:
            self.browser.quit()
            self.browser = None
            logging.info("Selenium WebDriver closed")

    def maybe_open_editor(self, filename: str) -> str:
        """Opens VSCode if not already open."""
        logging.debug(f"Attempting to open editor for {filename}...")
        try:
            if self.editor is None:
                editor_commands = ["code", "vscode", "codium"]
                for cmd in editor_commands:
                    try:
                        subprocess.Popen([cmd, filename])
                        self.editor = filename
                        logging.info(f"Editor opened for {filename}")
                        return f"Editor opened for {filename}"
                    except FileNotFoundError:
                        logging.warning(f"Editor command not found: {cmd}")
                        continue
                logging.error("Failed to open editor")
                return "Failed to open editor"
            logging.info(f"Editor already open with {filename}")
            return f"Editor already open with {filename}"
        except Exception as e:
            logging.error(f"Error opening editor: {e}")
            return f"Error opening editor: {str(e)}"

    def maybe_open_terminal(self) -> str:
        """Opens a terminal if not already open."""
        logging.debug("Attempting to open terminal...")
        try:
            if self.terminal is None:
                env = os.environ.copy()
                env["PS1"] = "$ "
                terminal_commands = [
                    ["alacritty", "-e", "sh"],
                    ["gnome-terminal", "--"],
                    ["xterm"],
                    ["terminal"]
                ]
                for cmd in terminal_commands:
                    try:
                        subprocess.Popen(cmd, env=env)
                        self.terminal = "terminal"
                        logging.info(f"Terminal opened using {cmd[0]}")
                        return f"Terminal opened using {cmd[0]}"
                    except FileNotFoundError:
                        logging.warning(f"Terminal command not found: {cmd[0]}")
                        continue
                logging.error("Failed to open terminal")
                return "Failed to open terminal"
            logging.info("Terminal already open")
            return "Terminal already open"
        except Exception as e:
            logging.error(f"Error opening terminal: {e}")
            return f"Error opening terminal: {str(e)}"

class SupremeAgent:
    """Enhanced Supreme Agent with browser, code, and terminal capabilities."""
    
    def __init__(self):
        self.swarm_client = Swarm()
        self.speech_client = OpenAI() 
        self.progress = TranslationProgress()
        self.system = SystemResources()
        self.available_tools = {}  
        self.setup_tools() 

    def setup_tools(self):
        """Set up available tools for agents."""
        
        def browser_open() -> str:
            """Opens a browser using Selenium WebDriver."""
            if self.system.setup_webdriver():
                return "WebDriver initialized successfully"
            else:
                return "Failed to initialize WebDriver"

        def browser_search(query: str) -> str:
            """Search Google with Selenium and retrieve the first search result."""
            return self.system.browser_search(query)

        def code_write(code: str, filename: str) -> str:
            """Write code to file using VSCode or directly."""
            try:
                with open(filename, 'w') as f:
                    f.write(code)
                self.system.maybe_open_editor(filename)
                return f"Code written to {filename}"
            except Exception as e:
                logging.error(f"Error writing code: {e}")
                return f"Error writing code: {str(e)}"
            
        def code_save(filename: str) -> str:
            """Save code file."""
            if os.path.exists(filename):
                return f"File {filename} saved"
            return f"File {filename} not found"

        def terminal_run(command: str) -> str:
            """Run command in terminal or directly."""
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True
                )
                return result.stdout or result.stderr or "Command executed"
            except Exception as e:
                logging.error(f"Command error: {e}")
                return f"Command error: {str(e)}"
            
        def git_command(command: str) -> str:
            """Run git commands."""
            return terminal_run(f"git {command}")

        def take_screenshot() -> str:
            """Capture a screenshot and return it as a base64 string."""
            try:
                screenshot = pyautogui.screenshot()
                buffered = BytesIO()
                screenshot.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                return img_str
            except Exception as e:
                logging.error(f"Screenshot error: {e}")
                return f"Screenshot error: {str(e)}"

        self.available_tools.update({
            'browser_open': browser_open,
            'browser_search': browser_search,
            'code_write': code_write,
            'code_save': code_save,
            'terminal_run': terminal_run,
            'git_command': git_command,
            'take_screenshot': take_screenshot,
        })

    def get_system_message(self, role: str) -> Dict[str, str]:
        """Retrieve the system message based on agent role."""
        if role == "search_agent":
            return {
                "role": "system",
                "content": """You are search_agent. Use the browser to perform a web search and retrieve the first result based on the user's query. Do not provide any explanations or summaries."""
            }
        elif role == "processing_agent":
            return {
                "role": "system",
                "content": """You are processing_agent. Your task is to take the search results provided, which include a title and a URL, and generate a concise and informative response for the user. Do not perform any web browsing or data fetching."""
            }
        elif role == "screenshot_agent":
            return {
                "role": "system",
                "content": """You are screenshot_agent. Your task is to take a screenshot of the first search result provided. Use the available tools to perform this action and return the screenshot as a base64-encoded string."""
            }
        else:
            return {
                "role": "system",
                "content": """You are a default_agent. Use available tools to complete the task."""
            }

    def create_specialized_agent(self, config: AgentConfig) -> Agent:
        """Create a specialized agent with specific tools."""
        agent_functions = {}
        for tool in config.tools:
            if tool in self.available_tools:
                agent_functions[tool] = self.available_tools[tool]
        
        return Agent(
            name=config.name,
            instructions=config.instructions,
            functions=agent_functions
        )

    def analyze_task(self, task: str) -> List[AgentConfig]:
        """Analyze task and create appropriate agent configurations."""
        try:
            if "search" in task.lower() or "find" in task.lower():
                return [
                    AgentConfig(
                        name="search_agent",
                        instructions="Use browser_search to find the requested information",
                        tools=["browser_search"],
                        next_agent=None
                    )
                ]
                
            response = self.speech_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a task analysis expert..."""
                    },
                    {
                        "role": "user",
                        "content": f"Analyze this task: {task}"
                    }
                ]
            )
            
            config_list = response.choices[0].message.content.strip()
            configs = json.loads(config_list)
            return [AgentConfig(**config) for config in configs]
                
        except Exception as e:
            logging.error(f"Task analysis error: {e}")
            return [AgentConfig(
                name="default_agent",
                instructions="Complete the task using available tools",
                tools=["browser_search"],
                next_agent=None
            )]



    def orchestrate_task(self, task: str, initial_input: Any) -> Any:
        """Orchestrate task execution through specialized agents."""
        logging.debug(f"Starting task orchestration for task: {task}")
        self.progress.start()
        
        try:
            agent_configs = self.analyze_task(task)
            current_input = initial_input
            
            for config in agent_configs:
                logging.info(f"Executing agent: {config.name}")
                
                # Create agent with proper tool access
                agent = self.create_specialized_agent(config)
                
                # Execute search
                if config.name == "search_agent":
                    result = agent.functions["browser_search"](current_input)
                    if "Error" not in result:
                        return result
                    logging.error(f"Search failed: {result}")
                
                # Handle other agent types
                messages = [
                    self.get_system_message(config.name),
                    {"role": "user", "content": str(current_input)}
                ]
                
                response = self.swarm_client.run(
                    agent=agent,
                    messages=messages
                )
                current_input = response.messages[-1]["content"]
                
            return current_input
            
        except Exception as e:
            logging.error(f"Task orchestration error: {e}")
            return f"Error executing task: {str(e)}"
        finally:
            self.progress.stop()
            self.system.close_webdriver()


    def run_interaction_loop(self):
        """Run the main Supreme Agent interface."""
        print("\nSupreme Agent with Browser and Code Capabilities")
        print("Available tasks:")
        print("1. Web search and research")
        print("2. Code development")
        print("3. Git operations")
        print("4. Custom task")
        print("Type 'exit' to quit\n")

        while True:
            try:
                task_input = input("> ")

                if task_input.lower() == 'exit':
                    print("Goodbye!")
                    break

                result = self.orchestrate_task(task_input, task_input)
                print("\nTask completed. Result:", result)
            except Exception as e:
                logging.error(f"Interaction error: {e}")
                print(f"Error: {str(e)}")
                print("Please try again or type 'exit' to quit")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        logging.info("Starting Supreme Agent application")
        supreme_agent = SupremeAgent()
        supreme_agent.run_interaction_loop()
    except Exception as e:
        logging.error(f"Application error: {e}")
        print(f"Fatal error: {str(e)}")
        sys.exit(1)