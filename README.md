# Fin Tracker

A powerful financial transaction tracking system that automatically extracts and analyzes financial transactions from your email inbox.

## 📋 Overview

Fin Tracker is a personal finance management tool that:

1. Connects to your Gmail account to scan for financial transaction emails
2. Uses AI (Google Gemini) to identify and extract transaction details
3. Stores transaction data in a local SQLite database
4. Provides a beautiful Streamlit dashboard for visualizing your spending patterns

## ✨ Features

- **Automated Email Processing**: Automatically scans your inbox for financial transactions
- **AI-Powered Analysis**: Uses Google Gemini to intelligently extract transaction details
- **Interactive Dashboard**: Visualize your spending with charts and filters
- **Privacy-Focused**: All data is stored locally on your machine
- **Customizable Categories**: Automatically categorizes transactions for better insights

## 📦 Prerequisites

- Python 3.8+
- Google account with Gmail
- Google Cloud Platform account (for API access)
- Gemini API key

## 🚀 Installation

1. **Clone the repository**

```bash
git clone https://github.com/yourusername/fin_tracker.git
cd fin_tracker
```

2. **Set up a virtual environment**

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Set up Google API credentials**

- Create a project in [Google Cloud Console](https://console.cloud.google.com/)
- Enable the Gmail API
- Create OAuth credentials (Desktop application)
- Download the credentials JSON file
- Create a `.secrets` directory and place the file as `.secrets/secrets.json`

5. **Set up environment variables**

Copy the example environment file and update it with your credentials:

```bash
cp .env.example .env
```

Edit the `.env` file to add your Gemini API key:

```
GEMINI_API_KEY=your_gemini_api_key_here
```

## 🔧 Configuration

The application uses several environment variables that can be configured in the `.env` file:

- `GEMINI_API_KEY`: Your Google Gemini API key
- `DB_PATH`: Path to the SQLite database (default: `finance_tracker.db`)
- `POLLING_INTERVAL`: How often to check for new emails in seconds (default: 3 hours)
- `MAX_RETRIES`: Maximum number of retries for API calls (default: 3)
- `RETRY_DELAY`: Delay between retries in seconds (default: 60)

## 🏃‍♂️ Usage

### Running the Email Processor

The email processor scans your inbox for transaction emails and stores them in the database:

```bash
python main.py
```

On first run, you'll be prompted to authorize the application to access your Gmail account.

### Running the Dashboard

To view your financial dashboard:

```bash
streamlit run streamlit_app.py
```

This will open a web browser with the interactive dashboard where you can:
- View spending by category
- Analyze monthly trends
- Filter transactions by date, amount, or category
- Search for specific transactions

## 📁 Project Structure

- `main.py`: Core email processing and database logic
- `streamlit_app.py`: Web dashboard interface
- `analyzer.py`: AI-powered email analysis and transaction extraction
- `tools.py`: Gmail API integration and utility functions
- `finance_tracker.db`: SQLite database for storing transactions
- `.secrets/`: Directory for storing Google API credentials
- `.attachments/`: Directory for storing email attachments

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.