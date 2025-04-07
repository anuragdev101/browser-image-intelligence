# browser-image-intelligence
Real-Time Screenshot Analyzer: A full-stack solution that captures browser screenshots with a Chrome Extension, processes them via AWS (S3, API Gateway, Lambda, DynamoDB) using CloudFormation, and leverages OpenAI’s GPT-4 for real-time image analysis.

# Real-Time Screenshot Analyzer

**Version:** 2.1 (Secured)

> **Disclaimer:** This project is designed solely for educational, accessibility, and research purposes. It is not intended for academic misconduct or cheating. Use responsibly.

---

## Overview

The Real-Time Screenshot Analyzer is a full-stack solution that captures browser screenshots via a Chrome Extension, processes them through an AWS-backed event-driven infrastructure, and analyzes the images using OpenAI’s GPT-4 (vision-enabled) model. The system is comprised of three major components:

1. **Chrome Extension:**  
   Captures screenshots of the active browser tab using a keyboard shortcut and uploads them to AWS via an HTTP API.

2. **Cloud Infrastructure (AWS):**  
   Implements a serverless, event-driven architecture using AWS services such as S3, API Gateway (WebSocket and HTTP APIs), Lambda functions, and DynamoDB. The infrastructure is provisioned via a CloudFormation template.

3. **Python Host Application:**  
   A desktop application built with Tkinter that connects to the AWS WebSocket, retrieves uploaded images from S3 via signed URLs, sends them to OpenAI for analysis, and displays the results.

This project demonstrates your expertise in modern web development, cloud infrastructure, real-time communication, and API integrations.

---

## Features

- **Real-Time Communication:**  
  Uses WebSockets to deliver near-instant notifications from the cloud to the host application.

- **Cloud-Backed Storage:**  
  Screenshots are securely stored in an AWS S3 bucket with controlled access via signed URLs.

- **Serverless Infrastructure:**  
  CloudFormation automates the deployment of AWS API Gateway, Lambda functions, and DynamoDB for managing WebSocket connections.

- **Advanced Image Analysis:**  
  Utilizes OpenAI’s GPT-4 vision model to analyze screenshots and extract text answers from multiple-choice questions.

- **Chrome Extension Integration:**  
  A lightweight extension that captures screenshots using background and content scripts, and communicates with the cloud APIs.

- **Security Focus:**  
  API key authentication, environment-based configuration (via `.env` files), and least-privilege IAM roles help secure the application.

---

## Architecture

### High-Level Diagram

            +-------------------+
            |   Chrome          |
            |   Extension       |  
            | (Screenshot, .env)|  
            +--------+----------+
                     | (Upload via HTTP API)
                     v
     +-------------------------------+
     |      AWS Cloud Infrastructure |
     |  (S3, API Gateway, Lambda,    |
     |   DynamoDB via CloudFormation)|
     +--------+-----------+----------+
              |  (Notifies via WebSocket)
              v
     +----------------------+
     | Python Host App      |
     | (Tkinter GUI,       |
     |  WebSocket client,   |
     |  OpenAI API caller)  |
     +----------------------+

## Repository Structure

/ (root) 

             ├── chrome-extension/ # Chrome extension files
		 │ ├── manifest.json # Extension manifest 
		 │ ├── background.js # Background script for capturing screenshots and API calls 
		 │ ├── content.js # Content script (if needed for DOM interactions) 
		 │ └── .env # Environment configuration for the extension 
		 ├── host_app.py # Python Host Application (Tkinter GUI & WebSocket client) 
		 ├── mcq_solver_infra.cfn.json # CloudFormation template for AWS infrastructure 
		 ├── requirements.txt # Python dependencies for the Host App 
		 └── README.md # This documentation file
		 
		 
- **host_app.py:**  
  Contains the Python code for initializing AWS S3 and OpenAI clients, managing WebSocket communication, and running the Tkinter GUI.
  
- **mcq_solver_infra.cfn.json:**  
  A CloudFormation template that sets up:
  - AWS API Gateway (WebSocket and HTTP APIs)
  - Lambda functions for connection handling, API key authorization, and image processing triggers
  - DynamoDB tables for managing WebSocket connections
  - S3 bucket for image uploads
  - IAM roles and permissions required for secure operation

- **.env:**  
  A local configuration file with environment variables for:
  - `OPENAI_API_KEY`
  - `WSS_URL`
  - `S3_BUCKET_NAME`
  - `OPENAI_MODEL`
  - `WEBSOCKET_SHARED_SECRET`

- **requirements.txt:**  
  Specifies all Python dependencies.

---

## Setup and Installation

### Prerequisites

- **General:**
  - An AWS account with permissions to deploy CloudFormation stacks.
  - API keys for OpenAI and AWS services.
  - Basic knowledge of Python, JavaScript, and AWS services.

- **Python Host App:**
  - Python 3.7+
  - Tkinter (typically included with Python)
  - Required packages (listed in `requirements.txt`)

- **Chrome Extension:**
  - Google Chrome browser (or any Chromium-based browser)

### 1. Deploy AWS Cloud Infrastructure

The CloudFormation template (`mcq_solver_infra.cfn.json`) now requires you to supply an API Gateway API key as a parameter. This key is used for authenticating requests to your API endpoints.

**Deployment Command:**

```bash
aws cloudformation deploy \
  --template-file mcq_solver_infra.cfn.json \
  --stack-name mcq-solver-infra \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides APIGatewayApiKey=YOUR_API_GATEWAY_API_KEY
```

Replace YOUR_API_GATEWAY_API_KEY with your desired API key value. After a successful deployment, note the CloudFormation outputs (e.g., WebSocket API endpoint, HTTP API endpoints, S3 bucket name) and update the corresponding values in your .env files.

### 2. Set Up the Chrome Extension

#### 1. Configuration:
	In the chrome-extension/.env file, configure the following environment variables:

	// Example content in chrome-extension/.env:
	HTTP_API_GET_UPLOAD_URL=YOUR_HTTP_API_GET_UPLOAD_URL
	HTTP_API_TRIGGER_URL=YOUR_HTTP_API_TRIGGER_URL
	WEBSOCKET_URL=YOUR_WEBSOCKET_API_ENDPOINT
	WEBSOCKET_SHARED_SECRET=YOUR_SHARED_SECRET

	Replace the placeholder values with the actual endpoints and secrets from your CloudFormation outputs.

#### 2. Load the Extension:

    Open Chrome and navigate to chrome://extensions/.
    Enable "Developer mode" (toggle in the upper right).
    Click on "Load unpacked" and select the chrome-extension/ directory.
    The extension should now be installed and ready to use.
	
### 3. Configure and Run the Python Host Application

#### 1. Environment Variables:
  Create a .env file in the project root (or update the existing one) with these keys:

  ```bash
  OPENAI_API_KEY=YOUR_OPEN_AI_API_KEY
  WSS_URL=YOUR_WEBSOCKET_URL
  S3_BUCKET_NAME=YOUR_S3_BUCKET_NAME
  OPENAI_MODEL=gpt-4o
  WEBSOCKET_SHARED_SECRET=YOUR_SHARED_SECRET
```

#### 2. Install Dependencies:
Set up a virtual environment (optional) and install required packages:

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 3. Run the Application:

```bash
python host_app.py
```

The Tkinter GUI will launch. Use the provided buttons to connect/disconnect the WebSocket and monitor log messages and results.

### 4. Usage Workflow

 ####   1. Chrome Extension:
  
    Use the extension to capture a screenshot (Ctrl + X).
    The extension uploads the image to AWS S3 using the HTTP API endpoints configured in the .env file.
    Once uploaded, the CloudFormation-managed infrastructure sends a WebSocket notification to connected host apps.

####    2. Python Host App:
  
    Connects to the WebSocket to listen for notifications.
    Upon receiving a message, downloads the corresponding image from S3.
    Sends the image to OpenAI’s GPT-4 for analysis.
    Displays the answer on the GUI and copies it to the clipboard.

####    3. Cloud Infrastructure:
  
    Manages API endpoints, WebSocket connections, and Lambda functions.
    Uses a DynamoDB table to track active WebSocket connections.
    Provides secured, signed URLs for S3 access.
    Validates incoming API calls using the API Gateway API key provided during deployment.

### 5 .Security Considerations

  #### 1. Sensitive Data:
    All sensitive configuration details (API keys, secrets) are stored in .env files and should never be committed to version control.

  #### 2. SSL Verification:
    Some client libraries disable SSL verification during development. Ensure SSL verification is enabled in production.

  #### 3. IAM and Permissions:
    The CloudFormation template enforces least-privilege access through carefully defined IAM roles and policies.

### 6. Troubleshooting

  #### 1.  Configuration Errors:
    Check both the extension and host app logs for errors related to missing or incorrect environment variables.

  #### 2.  WebSocket Issues:
    Ensure the WSS_URL and WEBSOCKET_SHARED_SECRET values are correctly set in both the extension and host app .env files.

  #### 3.  API Key Validation:
    Verify that your OpenAI API key, AWS credentials, and API Gateway API key are valid and that your AWS CloudFormation stack deployed correctly.

 #### 4.   Client-Side Issues:

    For Chrome Extension issues, use Chrome’s Developer Tools (Console and Network tabs) for debugging.
    For the Python Host App, review the console log and GUI log pane for details.

### 6 .License

This project is licensed under the MIT License.


---

### Final Notes

- **Customization:** Adjust endpoints, API keys, and other configuration details as required.
- **Diagram:** Consider adding an architecture diagram image in an `assets` folder and update the README accordingly.
- **Files:** Ensure that all sensitive files (like `.env`) are excluded from version control using a `.gitignore` file.

This README provides a detailed, professional overview of your project—including instructions on supplying the API Gateway API key as a CloudFormation parameter—making it ideal for GitHub and technical interviews.
