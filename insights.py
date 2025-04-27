def summarize_spending(df):
    return (
        df.groupby('category')['amount']
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={'amount': 'total_spent'})
    )
