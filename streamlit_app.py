import streamlit as st
import sqlite3
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from contextlib import contextmanager

# Set page configuration
st.set_page_config(
    page_title="Finance Tracker Dashboard",
    page_icon="💰",
    layout="wide"
)

# Custom CSS for better styling
st.markdown("""
<style>

    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #1f77b4;
    }
    .metric-label {
        font-size: 14px;
        color: #666;
    }

    .stDataFrame {
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
</style>
""", unsafe_allow_html=True)

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
            cursor.execute("SELECT * FROM transactions ORDER BY transaction_date DESC")
            rows = cursor.fetchall()
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


def preprocess_transactions(transactions):
    """Convert transactions to DataFrame and preprocess data"""
    if not transactions:
        return pd.DataFrame()
    
    df = pd.DataFrame(transactions)
    
    # Convert transaction_date to datetime
    df['transaction_date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
    
    # Extract month, year, day for aggregations
    df['month'] = df['transaction_date'].dt.month
    df['month_name'] = df['transaction_date'].dt.month_name()
    df['year'] = df['transaction_date'].dt.year
    df['day'] = df['transaction_date'].dt.day
    
    # Try to extract categories from description or subject
    # This is a simple approach - could be improved with NLP
    common_categories = ['food', 'grocery', 'restaurant', 'transport', 'uber', 'lyft', 
                        'shopping', 'amazon', 'utility', 'bill', 'subscription', 
                        'entertainment', 'salary', 'income', 'transfer']
    
    def extract_category(row):
        desc = str(row['description']).lower() if pd.notna(row['description']) else ""
        subj = str(row['subject']).lower() if pd.notna(row['subject']) else ""
        
        combined_text = f"{desc} {subj}"
        
        for category in common_categories:
            if category in combined_text:
                return category.title()
        
        # Check if it's income or expense based on amount
        if row['amount'] > 0:
            return 'Income'
        return 'Other Expense'
    
    df['category'] = df.apply(extract_category, axis=1)
    
    return df


def display_metrics(df):
    """Display key financial metrics"""
    if df.empty:
        return
    
    # Calculate metrics
    total_income = df[df['amount'] > 0]['amount'].sum()
    total_expenses = abs(df[df['amount'] < 0]['amount'].sum())
    net_cashflow = total_income - total_expenses
    # avg_transaction = df['amount'].mean()
    transaction_count = len(df)
    
    # Create 4 columns for metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">${total_income:.2f}</div>', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">Total Income</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">${total_expenses:.2f}</div>', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">Total Expenses</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        color = "green" if net_cashflow >= 0 else "red"
        st.markdown(f'<div class="metric-value" style="color:{color}">${net_cashflow:.2f}</div>', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">Net Cash Flow</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{transaction_count}</div>', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">Transactions</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


def create_time_series_chart(df):
    """Create time series chart of transactions"""
    if df.empty:
        return
    
    # Group by date and calculate daily sum
    daily_sum = df.groupby('transaction_date')['amount'].sum().reset_index()
    
    # Create time series chart
    fig = px.line(
        daily_sum, 
        x='transaction_date', 
        y='amount',
        title='Transaction Amount Over Time',
        labels={'transaction_date': 'Date', 'amount': 'Amount ($)'},
        template='plotly_white'
    )
    
    fig.update_layout(
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
        hovermode='x unified',
        xaxis_title='Date',
        yaxis_title='Amount ($)',
    )
    
    st.plotly_chart(fig, use_container_width=True)


def create_category_chart(df):
    """Create category-based charts"""
    if df.empty:
        return
    
    # Group by category
    category_data = df.groupby('category')['amount'].sum().reset_index()
    
    # Split into income and expenses
    income_data = category_data[category_data['amount'] > 0]
    expense_data = category_data[category_data['amount'] < 0].copy()
    expense_data['amount'] = expense_data['amount'].abs()  # Convert to positive for visualization
    
    # Create two columns
    col1, col2 = st.columns(2)
    
    with col1:
        # Income by category
        if not income_data.empty:
            fig = px.pie(
                income_data,
                values='amount',
                names='category',
                title='Income by Category',
                hole=0.4,
                color_discrete_sequence=px.colors.sequential.Greens
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No income data available")
    
    with col2:
        # Expenses by category
        if not expense_data.empty:
            fig = px.pie(
                expense_data,
                values='amount',
                names='category',
                title='Expenses by Category',
                hole=0.4,
                color_discrete_sequence=px.colors.sequential.Reds
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No expense data available")


def create_monthly_chart(df):
    """Create monthly income/expense chart"""
    if df.empty or 'month' not in df.columns:
        return
    
    # Group by month and year
    monthly_data = df.groupby(['year', 'month', 'month_name'])['amount'].agg(['sum', 'count']).reset_index()
    
    # Sort by year and month
    monthly_data = monthly_data.sort_values(['year', 'month'])
    
    # Create a column for month-year label
    monthly_data['month_year'] = monthly_data['month_name'] + ' ' + monthly_data['year'].astype(str)
    
    # Split into income and expenses
    monthly_data['income'] = monthly_data['sum'].apply(lambda x: max(x, 0))
    monthly_data['expense'] = monthly_data['sum'].apply(lambda x: abs(min(x, 0)))
    
    # Create the bar chart
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=monthly_data['month_year'],
        y=monthly_data['income'],
        name='Income',
        marker_color='green'
    ))
    
    fig.add_trace(go.Bar(
        x=monthly_data['month_year'],
        y=monthly_data['expense'],
        name='Expenses',
        marker_color='red'
    ))
    
    fig.update_layout(
        title='Monthly Income and Expenses',
        xaxis_title='Month',
        yaxis_title='Amount ($)',
        barmode='group',
        height=400,
        template='plotly_white',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)


# Initialize the database
init_db()

# App header
st.title('💰 Finance Tracker Dashboard')
st.markdown('_Visualize and analyze your financial transactions_')

# Sidebar for filters and maintenance operations
st.sidebar.header('Filters')

# Load transactions
transactions = load_transactions()
df_transactions = preprocess_transactions(transactions)

# Date filters
if not df_transactions.empty and 'transaction_date' in df_transactions.columns:
    min_date = df_transactions['transaction_date'].min().date()
    max_date = df_transactions['transaction_date'].max().date()
    
    date_range = st.sidebar.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    
    if len(date_range) == 2:
        start_date, end_date = date_range
        mask = (df_transactions['transaction_date'].dt.date >= start_date) & (df_transactions['transaction_date'].dt.date <= end_date)
        df_filtered = df_transactions[mask]
    else:
        df_filtered = df_transactions
else:
    df_filtered = df_transactions

# Category filter
if not df_filtered.empty and 'category' in df_filtered.columns:
    categories = ['All'] + sorted(df_filtered['category'].unique().tolist())
    selected_category = st.sidebar.selectbox("Category", categories)
    
    if selected_category != 'All':
        df_filtered = df_filtered[df_filtered['category'] == selected_category]

# Amount range filter
if not df_filtered.empty:
    min_amount = float(df_filtered['amount'].min())
    max_amount = float(df_filtered['amount'].max())
    
    amount_range = st.sidebar.slider(
        "Amount Range ($)",
        min_value=min_amount,
        max_value=max_amount,
        value=(min_amount, max_amount),
        step=10.0
    )
    
    df_filtered = df_filtered[(df_filtered['amount'] >= amount_range[0]) & (df_filtered['amount'] <= amount_range[1])]

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

# Main content area
if not df_filtered.empty:
    # Display metrics
    st.markdown("### Key Metrics")
    display_metrics(df_filtered)
    
    # Time series visualization
    st.markdown("### Transaction Trends")
    with st.container():
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        create_time_series_chart(df_filtered)
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Monthly breakdown
    st.markdown("### Monthly Breakdown")
    with st.container():
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        create_monthly_chart(df_filtered)
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Category visualization
    st.markdown("### Category Analysis")
    with st.container():
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        create_category_chart(df_filtered)
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Transactions table
    st.markdown("### Transaction Details")
    with st.expander("View All Transactions", expanded=False):
        # Select only relevant columns for display
        display_cols = ['transaction_date', 'description', 'amount', 'category', 'from_email', 'subject']
        display_df = df_filtered[display_cols].copy()
        
        # Format the date column
        display_df['transaction_date'] = display_df['transaction_date'].dt.strftime('%Y-%m-%d')
        
        # Format the amount column
        display_df['amount'] = display_df['amount'].apply(lambda x: f"${x:.2f}")
        
        st.dataframe(display_df, use_container_width=True)
else:
    st.info('No transactions found. Add some transactions to see visualizations.') 