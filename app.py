import streamlit as st
from parser import load_all_transactions

df = load_all_transactions()

# Separate views
checking_df = df[df['account_type'] == 'checking']
credit_df = df[df['account_type'] == 'credit']

# UI mode toggle
mode = st.radio("🧭 View Mode", ["Unified Table", "Side-by-Side Tables"])

if mode == "Unified Table":
    st.title("📊 All Transactions (Unified)")
    st.dataframe(df)

elif mode == "Side-by-Side Tables":
    col1, col2 = st.columns(2)

    with col1:
        show_checking = st.checkbox("Show Checking", value=True)
        if show_checking:
            st.subheader("🏦 Checking")
            st.dataframe(checking_df)

    with col2:
        show_credit = st.checkbox("Show Credit", value=True)
        if show_credit:
            st.subheader("💳 Credit Card")
            st.dataframe(credit_df)
