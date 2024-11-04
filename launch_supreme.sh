#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_message() {
    echo -e "${BLUE}[Supreme Agent]${NC} $1"
}

# Function to print warnings
print_warning() {
    echo -e "${YELLOW}[Warning]${NC} $1"
}

# Function to print errors
print_error() {
    echo -e "${RED}[Error]${NC} $1"
}

# Function to check Python version
check_python_version() {
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    required_version="3.10"
    
    if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
        print_error "Python version $required_version or higher is required. Current version: $python_version"
        print_message "Please install Python $required_version or higher and try again."
        exit 1
    fi
}

# Function to check if Python is installed
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed. Please install Python 3 and try again."
        exit 1
    fi
    check_python_version
}

# Function to check for necessary audio dependencies
check_audio_deps() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if ! brew list portaudio > /dev/null 2>&1; then
            print_warning "PortAudio not found. Installing..."
            brew install portaudio
        fi
    elif [ -f "/etc/debian_version" ]; then
        if ! dpkg -l | grep -q "libportaudio2"; then
            sudo apt-get update
            sudo apt-get install -y libportaudio2 libportaudiocpp0 portaudio19-dev
        fi
    elif [ -f "/etc/redhat-release" ]; then
        if ! rpm -q portaudio-devel > /dev/null 2>&1; then
            sudo yum install -y portaudio portaudio-devel
        fi
    fi
}

# Function to setup virtual environment
setup_venv() {
    if [ ! -d "venv" ]; then
        print_message "Creating virtual environment..."
        python3 -m venv venv
        if [ $? -ne 0 ]; then
            print_error "Failed to create virtual environment."
            exit 1
        fi
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    if [ $? -ne 0 ]; then
        print_error "Failed to activate virtual environment."
        exit 1
    fi
}

# Function to install local swarm mock
create_swarm_mock() {
    mkdir -p swarm_mock
    cat > swarm_mock/setup.py << EOL
from setuptools import setup, find_packages

setup(
    name="swarm",
    version="0.1.0",
    packages=find_packages(),
)
EOL

    mkdir -p swarm_mock/swarm
    cat > swarm_mock/swarm/__init__.py << EOL
class Agent:
    def __init__(self, name, instructions, functions=None):
        self.name = name
        self.instructions = instructions
        self.functions = functions or []

class Swarm:
    def __init__(self):
        pass
        
    def run(self, agent, messages, context_variables=None):
        from openai import OpenAI
        client = OpenAI()
        
        formatted_messages = []
        formatted_messages.append({"role": "system", "content": f"You are {agent.name}. {agent.instructions}"})
        formatted_messages.extend(messages)
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=formatted_messages
        )
        
        class MockResponse:
            def __init__(self, messages):
                self.messages = messages
                
        return MockResponse([{"role": "assistant", "content": response.choices[0].message.content}])
EOL

    # Install the mock package
    pip install -e swarm_mock
}

# Function to install dependencies
install_dependencies() {
    print_message "Installing system dependencies..."
    check_audio_deps
    
    print_message "Installing Python dependencies..."
    pip install --upgrade pip
    
    # Create and install requirements.txt
    cat > requirements.txt << EOL
openai>=1.0.0
pyaudio>=0.2.13
simpleaudio>=1.0.4
wave>=0.0.2
pytest>=7.4.0
pytest-mock>=3.11.1
pytest-cov>=4.1.0
black>=23.7.0
isort>=5.12.0
flake8>=6.1.0
EOL
    
    # Install dependencies
    pip install -r requirements.txt
    
    # Set up Swarm mock
    print_message "Setting up Swarm implementation..."
    create_swarm_mock
    
    if [ $? -ne 0 ]; then
        print_error "Failed to install dependencies."
        exit 1
    fi
}

# Function to check dependencies
check_dependencies() {
    local missing_deps=0
    
    for package in "openai" "pyaudio" "simpleaudio" "wave" "swarm"; do
        if ! python3 -c "import $package" 2>/dev/null; then
            print_warning "$package package not found."
            missing_deps=1
        fi
    done
    
    if [ $missing_deps -eq 1 ]; then
        print_message "Installing missing dependencies..."
        install_dependencies
    fi
}

# Function to run tests
run_tests() {
    print_message "Running tests..."
    pytest -v test_supreme_agent.py
    if [ $? -eq 0 ]; then
        print_message "All tests passed successfully!"
    else
        print_error "Some tests failed. Please check the output above."
    fi
}

# Function to run the application
run_app() {
    print_message "Checking dependencies..."
    check_dependencies
    
    print_message "Launching Supreme Agent..."
    python3 supreme_agent.py
}

# Main menu function
show_menu() {
    clear
    echo -e "${GREEN}=== Supreme Agent Launcher ===${NC}"
    echo "1. Run Supreme Agent"
    echo "2. Run Tests"
    echo "3. Install/Update Dependencies"
    echo "4. Exit"
    echo
    read -p "Please select an option (1-4): " choice
    
    case $choice in
        1)
            run_app
            ;;
        2)
            run_tests
            ;;
        3)
            install_dependencies
            ;;
        4)
            print_message "Goodbye!"
            deactivate 2>/dev/null
            exit 0
            ;;
        *)
            print_error "Invalid option. Please try again."
            sleep 2
            show_menu
            ;;
    esac
}

# Main script execution
main() {
    # Check if running from correct directory
    if [ ! -f "supreme_agent.py" ]; then
        print_error "Please run this script from the Supreme Agent directory."
        exit 1
    fi

    # Initial setup
    check_python
    setup_venv
    
    # Show menu until exit
    while true; do
        show_menu
        echo
        read -p "Press Enter to continue..."
    done
}

# Run main function
main