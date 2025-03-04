import sqlite3
import time
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging
from contextlib import contextmanager

from tools import GmailClient, EmailType
from analyzer import EmailAnalyzer

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("finance_tracker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Configuration ---
DB_PATH = os.environ.get("DB_PATH", "finance_tracker.db")
POLLING_INTERVAL = int(os.environ.get("POLLING_INTERVAL", 3 * 60 * 60))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
RETRY_DELAY = int(os.environ.get("RETRY_DELAY", 60))

# --- SQLite Database Setup ---
@contextmanager
def get_db_connection():
    """Context manager for database connections to ensure proper closing."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    """Initialize the SQLite database with the transactions table."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id TEXT UNIQUE,
                    thread_id TEXT,
                    from_email TEXT,
                    transaction_date TEXT,
                    amount REAL,
                    description TEXT,
                    category TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        raise

def store_transaction(transaction: Dict) -> bool:
    """
    Store a transaction in the SQLite database.
    Returns True if successful, False otherwise.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO transactions (
                    email_id, thread_id, from_email, transaction_date, amount, description, category
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                transaction["email_id"],
                transaction["thread_id"],
                transaction["from_email"],
                transaction["transaction_date"],
                transaction["amount"],
                transaction["description"],
                transaction.get("category", "")
            ))
            
            conn.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Stored transaction (ID: {transaction['email_id']})")
                return True
            else:
                logger.info(f"Transaction already exists for email: {transaction['email_id']}")
                return False
    except sqlite3.Error as e:
        logger.error(f"Database error storing transaction: {e}", exc_info=True)
        return False
    except KeyError as e:
        logger.error(f"Missing key in transaction data: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error storing transaction: {e}", exc_info=True)
        return False

def email_already_processed(email_id: str) -> bool:
    """Check if an email id has already been processed and stored in the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM transactions WHERE email_id = ?", (email_id,))
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking if email is processed: {e}")
        return False

def get_last_processed_time() -> Optional[datetime]:
    """
    Get the timestamp of the most recently processed email.
    Returns None if no emails have been processed.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(transaction_date) as last_date FROM transactions
            """)
            result = cursor.fetchone()
            if result and result['last_date']:
                return datetime.fromisoformat(result['last_date'])
            return None
    except (sqlite3.Error, ValueError) as e:
        logger.error(f"Error retrieving last processed time: {e}")
        return None
    
def run_finance_tracker(email_address: str):
    logger.info("Starting finance tracker")
    init_db()
    client = GmailClient()
    
    while True:
        try:
            end_time = datetime.now()
            last_processed_time = get_last_processed_time()
            start_time = last_processed_time or (end_time - timedelta(hours=24))
            if last_processed_time:
                start_time -= timedelta(minutes=10)
            
            logger.info(f"Fetching emails from {start_time} to {end_time}")
            emails = client.fetch_emails(
                email_address=email_address,
                start_time=start_time,
                end_time=end_time,
                email_type=EmailType.ALL,
                download_attachments=True
            )
            logger.info(f"Raw emails fetched: {len(emails)}")
            
            if not emails:
                logger.info("No new emails found")
            else:
                for email in emails:
                    if email_already_processed(email['id']):
                        logger.info(f"Email already processed: {email['id']}. Skipping.")
                        continue
                    logger.info(f"Processing email: {email['subject']} (ID: {email['id']})")
                    transaction = EmailAnalyzer.analyze_email(email)
                    if transaction:
                        logger.info(f"Transaction extracted: {transaction}")
                        success = store_transaction(transaction)
                        if success:
                            logger.info("Transaction stored successfully")
                        else:
                            logger.warning("Transaction storage failed or duplicate")
                    else:
                        logger.info("No transaction found in email")
            
            time.sleep(POLLING_INTERVAL)
        except Exception as e:
            logger.error(f"Error in loop: {e}", exc_info=True)
            time.sleep(RETRY_DELAY)

# --- Example Usage ---
# if __name__ == "__main__":
#     import argparse
    
#     parser = argparse.ArgumentParser(description="Finance Tracker - Email Transaction Analyzer")
#     parser.add_argument("--email", required=True, help="Email address to monitor")
#     parser.add_argument("--interval", type=int, help="Polling interval in hours (default: 24)")
#     parser.add_argument("--db", help="Path to SQLite database file (default: finance_tracker.db)")
    
#     args = parser.parse_args()
    
#     if args.interval:
#         os.environ["POLLING_INTERVAL"] = str(args.interval * 60 * 60)
    
#     if args.db:
#         os.environ["DB_PATH"] = args.db
    
#     run_finance_tracker(args.email)