import json
import time
import os
import logging
from typing import Dict, Optional
from dotenv import load_dotenv

from agno.agent import Agent, RunResponse
from agno.models.google import Gemini
from pydantic import BaseModel, Field, ValidationError

load_dotenv()

# --- Setup Logging ---
logger = logging.getLogger(__name__)

# --- Configuration ---
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
RETRY_DELAY = int(os.environ.get("RETRY_DELAY", 60))  # Default: 60 seconds

# --- Transaction Pydantic Model ---
class TransactionData(BaseModel):
    email_id: str = Field(..., description="The unique ID of the email.")
    thread_id: str = Field(..., description="The thread ID of the email conversation.")
    from_email: str = Field(..., description="The sender's email address.")
    subject: str = Field(..., description="The subject line of the email.")
    transaction_date: str = Field(..., description="The date of the transaction in ISO format.")
    amount: float = Field(..., description="The transaction amount extracted from the email.")
    description: str = Field(..., description="A brief description of the transaction.")
    raw_data: str = Field(..., description="The full email data as a JSON string.")


# --- AI Agent Setup ---
transaction_agent = Agent(
    model=Gemini(id="gemini-2.0-flash",api_key=os.getenv("GEMINI_API_KEY")),
    response_model=TransactionData,
    structured_outputs=True,
)

# --- AI Analysis Function ---
def analyze_email_with_ai(email: Dict) -> Optional[Dict]:
    """
    Analyze an email using an AI agent to extract transaction details.
    Returns a dict with transaction data if found, else None.
    """
    required_keys = ['id', 'thread_id', 'from_email', 'to_email', 'subject', 'send_time', 'page_content']
    missing_keys = [key for key in required_keys if key not in email]
    if missing_keys:
        logger.error(f"Email is missing required keys: {missing_keys}. Skipping email.")
        return None
    
    logger.info(f"Analyzing email: {email['subject']} (ID: {email['id']})")
    
    for attempt in range(MAX_RETRIES):
        try:
            # Prepare the input prompt with email content
            prompt = (
                f"Analyze the following email and extract transaction details if present:\n\n"
                f"From: {email['from_email']}\n"
                f"To: {email['to_email']}\n"
                f"Subject: {email['subject']}\n"
                f"Date: {email['send_time']}\n"
                f"Body:\n{email['page_content']}\n\n"
                f"If this email contains a financial transaction, extract the details and return them in a structured format. "
                f"If no transaction is found, return None. "
                f"For transaction_date, use ISO format (YYYY-MM-DD)."
            )


            # Get structured response from the AI agent
            response: RunResponse = transaction_agent.run(prompt)
            
            # Handle the response
            if response is None or response.content is None:
                logger.info(f"No transaction found in email: {email['id']}")
                return None
                
            # Check if the response is an instance of TransactionData
            if not isinstance(response.content, TransactionData):
                logger.warning(f"Unexpected response type from AI agent: {type(response.content)}")
                return None
            
            # Convert Pydantic model to dict
            transaction_dict = response.content.model_dump()
            
            # Ensure email_id and thread_id match the actual email
            transaction_dict["email_id"] = email["id"]
            transaction_dict["thread_id"] = email["thread_id"]
            
            # Add full email data as JSON string
            transaction_dict["raw_data"] = json.dumps(email)
            
            logger.info(f"Successfully extracted transaction from email: {email['id']}")
            return transaction_dict
            
        except ValidationError as e:
            logger.error(f"Validation error for email {email['id']}: {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying analysis (attempt {attempt + 2}/{MAX_RETRIES})...")
                time.sleep(RETRY_DELAY)
            else:
                return None
            
        except Exception as e:
            logger.error(f"Error analyzing email {email['id']}: {e}", exc_info=True)
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying analysis (attempt {attempt + 2}/{MAX_RETRIES})...")
                time.sleep(RETRY_DELAY)
            else:
                return None
    
    return None