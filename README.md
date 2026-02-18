# Application Task Agent

## Description

Application Task Agent is an intelligent automation framework designed to orchestrate, remediate, and manage application tasks using a modular, node-based graph system. It integrates with Splunk for log analysis, supports database-backed state management, and leverages LLMs for remediation generation. The agent is extensible and suitable for automating complex operational flows in cloud-native environments.

## Features
- Modular node-based graph execution
- Automated remediation generation
- Splunk integration for log search and summarization
- Database-backed state and resolution management
- Extensible utility and tool modules
- Async flow support

## Prerequisites
- Python 3.10 or higher (recommended: Python 3.13)
- pip (Python package manager)
- Access to Splunk (for log search features)
- (Optional) Virtual environment tool (venv, virtualenv)

## Setup

1. **Clone the repository**
   ```cmd
   git clone <your-repo-url>
   cd application-task-agent
   ```

2. **Create and activate a virtual environment (recommended)**
   ```cmd
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies**
   ```cmd
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   - Create a `.env` file in the project root directory.
   - Add required variables (e.g., Splunk credentials, database connection info) to `.env`.
   - Example:
     ```env
     OPENAI_API_KEY=your_openai_key
     OPENAI_MODEL_CLASSIFY = gpt-4.1-mini
     OPENAI_MODEL_AGENT = gpt-4.1-mini
     ```
   - Update `app/utility/config.py` to load variables from `.env` as needed.

## Usage

### Start the Agent
Run the main entry point:
```cmd
python main.py
```

### Run Tests
Execute the test suite to verify functionality:
```cmd
python -m unittest discover test
```
Or run a specific test:
```cmd
python test\test_flow.py
```

## Project Structure
```
application-task-agent/
├── agent.py                # Main agent logic
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
├── app/                    # Core application modules
│   ├── nodes/              # Node implementations
│   ├── tools/              # External tool integrations
│   └── utility/            # Utility functions and configs
├── graph/                  # Graph builder and logic
├── store/                  # Database and persistence
├── test/                   # Test suite
```

## Extending the Agent
- Add new nodes in `app/nodes/` for custom actions.
- Integrate new tools in `app/tools/`.
- Update graph logic in `graph/graph_builder.py`.

## Troubleshooting
- Ensure Python version compatibility.
- Check `config.py` for correct credentials.
- Review logs and test output for error details.

## Contributing
Pull requests and issues are welcome! Please follow standard Python style guidelines and include tests for new features.

## License
This project is licensed under the MIT License.

## Contact
For questions or support, contact the maintainer at hasratp@aditiconsulting.com.
