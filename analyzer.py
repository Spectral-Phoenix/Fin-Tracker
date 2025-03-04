import json
import logging
import os
import time
from typing import Dict, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

# Assuming these are external dependencies
from agno.agent import Agent, RunResponse
from agno.models.google import Gemini

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Configuration constants
class Config:
    MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
    RETRY_DELAY = int(os.environ.get("RETRY_DELAY", 60))

# Email Classification Model
class EmailClassification(BaseModel):
    """Model representing the classification of an email as transactional or not."""
    is_transactional: bool = Field(..., description="Whether the email contains a financial transaction")
    confidence: float = Field(..., description="Confidence score (0.0-1.0) of the classification", ge=0.0, le=1.0)
    reasoning: str = Field(..., description="Brief explanation for the classification decision")

# Transaction Data Model
class TransactionData(BaseModel):
    """Model representing extracted transaction data from an email."""
    email_id: str = Field(..., description="Unique identifier of the email")
    thread_id: str = Field(..., description="Email conversation thread identifier")
    from_email: str = Field(..., description="Sender's email address")
    subject: str = Field(..., description="Email subject line")
    transaction_date: str = Field(..., description="Transaction date in ISO format (YYYY-MM-DD)")
    amount: float = Field(..., description="Transaction amount as a float value")
    description: str = Field(..., description="Brief transaction description (max 100 characters)", max_length=100)
    raw_data: str = Field(..., description="Complete email data as JSON string")

# Initialize AI Agents
classifier_agent = Agent(
    model=Gemini(
        id="gemini-2.0-flash",
        api_key=os.getenv("GEMINI_API_KEY")
    ),
    response_model=EmailClassification,
    structured_outputs=True,
)

extractor_agent = Agent(
    model=Gemini(
        id="gemini-2.0-flash",
        api_key=os.getenv("GEMINI_API_KEY")
    ),
    response_model=TransactionData,
    structured_outputs=True,
)

class EmailAnalyzer:
    """Class responsible for analyzing emails and extracting transaction information."""
    
    REQUIRED_KEYS = {'id', 'thread_id', 'from_email', 'to_email', 'subject', 'send_time', 'page_content'}
    
    @staticmethod
    def _validate_email(email: Dict) -> Optional[list[str]]:
        """Validate that email contains all required keys."""
        missing_keys = [key for key in EmailAnalyzer.REQUIRED_KEYS if key not in email]
        if missing_keys:
            logger.error(f"Email missing required keys: {missing_keys}")
            return missing_keys
        return None

    @staticmethod
    def _build_classification_prompt(email: Dict) -> str:
        """Construct the classification prompt for the AI agent."""
        return (
            "TASK: Determine if the following email contains a financial transaction.\n\n"
            f"From: {email['from_email']}\n"
            f"To: {email['to_email']}\n"
            f"Subject: {email['subject']}\n"
            f"Date: {email['send_time']}\n"
            f"Body:\n{email['page_content']}\n\n"
            "CLASSIFICATION GUIDELINES:\n"
            "1. FINANCIAL TRANSACTION INDICATORS:\n"
            "   - Monetary amounts (e.g., $10.99, €50, 100 USD)\n"
            "   - Payment confirmation language (e.g., 'Your payment was successful')\n"
            "   - Receipt or invoice terminology\n"
            "   - Order confirmations with prices\n"
            "   - Subscription charges or renewals\n"
            "   - Bill payment confirmations\n"
            "   - Banking transaction notifications\n\n"
            "2. NON-TRANSACTION INDICATORS:\n"
            "   - Marketing or promotional emails (even if they mention prices)\n"
            "   - General correspondence without financial activity\n"
            "   - Account notifications without monetary transactions\n"
            "   - Shipping notifications without payment details\n"
            "   - Password resets or security alerts\n"
            "   - Newsletters or informational updates\n\n"
            "3. CONFIDENCE ASSESSMENT:\n"
            "   - High confidence (0.8-1.0): Clear transaction details present\n"
            "   - Medium confidence (0.5-0.79): Some transaction indicators but ambiguous\n"
            "   - Low confidence (0.0-0.49): Few or no transaction indicators\n\n"
            "OUTPUT REQUIREMENTS:\n"
            "- is_transactional: true/false based on presence of financial transaction\n"
            "- confidence: Score between 0.0-1.0 indicating classification confidence\n"
            "- reasoning: Brief explanation (1-3 sentences) justifying your classification\n"
        )

    @staticmethod
    def _build_extraction_prompt(email: Dict) -> str:
        """Construct the extraction prompt for the AI agent."""
        return (
            "TASK: Extract detailed financial transaction information from the following email.\n\n"
            f"From: {email['from_email']}\n"
            f"To: {email['to_email']}\n"
            f"Subject: {email['subject']}\n"
            f"Date: {email['send_time']}\n"
            f"Body:\n{email['page_content']}\n\n"
            "EXTRACTION GUIDELINES:\n"
            "1. TRANSACTION DATE:\n"
            "   - Format as ISO 8601 (YYYY-MM-DD)\n"
            "   - Extract the actual transaction date, not email date\n"
            "   - If multiple dates present, select the one associated with the transaction\n"
            "   - If no specific date found, use the email date as fallback\n\n"
            "2. AMOUNT:\n"
            "   - Extract as float value only (e.g., 29.99, not $29.99)\n"
            "   - For multiple amounts, identify the primary transaction amount\n"
            "   - Convert foreign currencies if exchange rate is provided\n"
            "   - For refunds or credits, use positive value and indicate in description\n\n"
            "3. DESCRIPTION:\n"
            "   - Create concise but informative summary (max 100 characters)\n"
            "   - Include merchant/sender name and transaction type\n"
            "   - Format as: [Transaction Type] - [Merchant] - [Item/Service]\n"
            "   - Examples: 'Payment - Netflix - Monthly Subscription', 'Purchase - Amazon - Headphones'\n\n"
            "4. ADDITIONAL FIELDS:\n"
            "   - email_id: Use the provided email ID\n"
            "   - thread_id: Use the provided thread ID\n"
            "   - from_email: Extract the sender's email address\n"
            "   - subject: Use the email subject line\n\n"
            "OUTPUT REQUIREMENTS:\n"
            "- Provide all TransactionData fields with accurate information\n"
            "- Ensure values match the specified formats and constraints\n"
            "- If a required field cannot be determined with certainty, make a reasonable inference\n"
        )

    @classmethod
    def analyze_email(cls, email: Dict) -> Optional[Dict]:
        """
        Analyze an email to extract transaction details using a two-step AI approach.
        
        Args:
            email: Dictionary containing email data
            
        Returns:
            Dictionary with transaction data if found, None otherwise
        """
        # Validate email structure
        if cls._validate_email(email):
            return None

        logger.info(f"Analyzing email: {email['subject']} (ID: {email['id']})")
        
        # Step 1: Classify if the email contains a transaction
        classification = cls._classify_email(email)
        if not classification or not classification.get('is_transactional'):
            logger.info(f"Email classified as non-transactional: {email['id']} (Confidence: {classification.get('confidence', 0) if classification else 0})")
            return None
            
        # Step 2: Extract transaction details
        transaction = cls._extract_transaction(email)
        if transaction:
            logger.info(f"Transaction extracted from email: {email['id']}")
            return transaction
            
        return None
        
    @classmethod
    def _classify_email(cls, email: Dict) -> Optional[Dict]:
        """Classify if an email contains a financial transaction."""
        prompt = cls._build_classification_prompt(email)
        
        for attempt in range(Config.MAX_RETRIES):
            try:
                response: RunResponse = classifier_agent.run(prompt)
                
                if not response or not response.content:
                    logger.warning(f"No classification response for email: {email['id']}")
                    return None

                if not isinstance(response.content, EmailClassification):
                    logger.warning(f"Unexpected classification response type: {type(response.content)}")
                    return None

                classification = response.content.model_dump()
                logger.info(f"Email classification: is_transactional={classification['is_transactional']}, confidence={classification['confidence']}")
                return classification

            except ValidationError as e:
                logger.error(f"Classification validation error for email {email['id']}: {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    logger.info(f"Retrying classification (attempt {attempt + 2}/{Config.MAX_RETRIES})")
                    time.sleep(Config.RETRY_DELAY)
                else:
                    return None

            except Exception as e:
                logger.error(f"Classification error for email {email['id']}: {e}", exc_info=True)
                if attempt < Config.MAX_RETRIES - 1:
                    logger.info(f"Retrying classification (attempt {attempt + 2}/{Config.MAX_RETRIES})")
                    time.sleep(Config.RETRY_DELAY)
                else:
                    return None
                    
        return None
        
    @classmethod
    def _extract_transaction(cls, email: Dict) -> Optional[Dict]:
        """Extract transaction details from an email."""
        prompt = cls._build_extraction_prompt(email)
        
        for attempt in range(Config.MAX_RETRIES):
            try:
                response: RunResponse = extractor_agent.run(prompt)
                
                if not response or not response.content:
                    logger.warning(f"No extraction response for email: {email['id']}")
                    return None

                if not isinstance(response.content, TransactionData):
                    logger.warning(f"Unexpected extraction response type: {type(response.content)}")
                    return None

                # Prepare transaction data
                transaction = response.content.model_dump()
                transaction.update({
                    "email_id": email["id"],
                    "thread_id": email["thread_id"],
                    "raw_data": json.dumps(email)
                })

                return transaction

            except ValidationError as e:
                logger.error(f"Extraction validation error for email {email['id']}: {e}")
                if attempt < Config.MAX_RETRIES - 1:
                    logger.info(f"Retrying extraction (attempt {attempt + 2}/{Config.MAX_RETRIES})")
                    time.sleep(Config.RETRY_DELAY)
                else:
                    return None

            except Exception as e:
                logger.error(f"Extraction error for email {email['id']}: {e}", exc_info=True)
                if attempt < Config.MAX_RETRIES - 1:
                    logger.info(f"Retrying extraction (attempt {attempt + 2}/{Config.MAX_RETRIES})")
                    time.sleep(Config.RETRY_DELAY)
                else:
                    return None
                    
        return None