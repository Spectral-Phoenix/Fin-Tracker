import streamlit as st
import sqlite3
import os
from contextlib import contextmanager

# Set default DB path
DB_PATH = os.environ.get('DB_PATH', 'finance_tracker.db')

@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        st.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()


def load_transactions():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM transactions ORDER BY created_at DESC")
            rows = cursor.fetchall()
            st.write(f"Found {len(rows)} transactions in database")  # Debug output
            return [dict(row) for row in rows]
    except Exception as e:
        st.error(f"Error loading transactions: {e}")
        return []


def clear_transactions():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM transactions")
            conn.commit()
            st.success("All transactions cleared.")
    except Exception as e:
        st.error(f"Error clearing transactions: {e}")


def init_db():
    # Ensure the transactions table exists
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id TEXT UNIQUE,
                    thread_id TEXT,
                    from_email TEXT,
                    subject TEXT,
                    transaction_date TEXT,
                    amount REAL,
                    description TEXT,
                    raw_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    except Exception as e:
        st.error(f"Error initializing database: {e}")


# Initialize the database
init_db()

st.title('Finance Tracker Dashboard')
st.write('Minimalistic interface to view and manage transactions.')

# Sidebar for maintenance operations
st.sidebar.header('Maintenance')

if st.sidebar.button('Refresh Data'):
    st.rerun()

# Create a checkbox for confirmation when clearing transactions
clear_confirm = st.sidebar.checkbox('Confirm Clear All Transactions')

if st.sidebar.button('Clear All Transactions'):
    if clear_confirm:
        clear_transactions()
        st.rerun()
    else:
        st.sidebar.error('Please confirm by checking the box before clearing.')

# Load and display transactions
transactions = load_transactions()

if transactions:
    st.subheader('Transactions')
    st.dataframe(transactions)
else:
    st.write('No transactions found.') 