import pandas as pd
import os
import traceback

import json

def load_vendor_cache(path="vendors.json"):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def save_vendor_cache(cache, path="vendors.json"):
    with open(path, 'w') as f:
        json.dump(cache, f, indent=2)

def get_category(description, cache):
    for vendor in cache:
        if vendor in description:
            return cache[vendor]
    return None


def load_and_clean_chase_csv(filepath, account_type):
    print(f"🔍 Attempting to read {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            print("🔎 First 5 lines of the file:")
            for _ in range(5):
                print(f.readline().strip())
    except Exception as e:
        print(f"❌ File read failed before pandas: {e}")
        raise

    try:
        df = pd.read_csv(filepath, encoding='utf-8-sig', engine='python')
    except Exception as e:
        print(f"❌ pd.read_csv() failed: {e}")
        raise

    print(f"📊 Columns: {df.columns.tolist()}")
    ...


    df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')

    # Try known column names
    date_col = None
    for col in df.columns:
        if col in ['post_date', 'posting_date', 'transaction_date']:
            date_col = col
            break

    # If not found, look for any column that includes the word 'date'
    if date_col is None:
        for col in df.columns:
            if 'date' in col:
                date_col = col
                print(f"⚠️ Using fallback date column: {col}")
                break

    if date_col is None:
        raise ValueError("❌ No recognizable date column found.")

    # Log and clean date column
    print(f"🗓️ Using date column: {date_col}")
    df[date_col] = df[date_col].astype(str).str.strip()

    df['date'] = pd.to_datetime(df[date_col], format='%m/%d/%Y', errors='coerce').dt.date

    if 'amount' not in df.columns:
        raise ValueError("❌ 'amount' column not found")

    df['amount'] = df['amount'].astype(str).str.replace(r'[\$,]', '', regex=True)
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')

    if account_type == 'credit':
        df['amount'] = df['amount'].apply(lambda x: -abs(x))

    df['description'] = df['description'].astype(str).str.strip().str.upper()
    df['account_type'] = account_type

    df['source_file'] = os.path.basename(filepath)
    df.to_json(f'cleaned_{account_type}.json', orient='records', indent=2)

    return df[['date', 'description', 'amount', 'account_type', 'source_file']]



def load_all_transactions(data_folder='data'):
    all_dfs = []
    print(f"📂 Checking directory: {data_folder}")
    print(f"📄 Files: {os.listdir(data_folder)}")

    for file in os.listdir(data_folder):
        if file.lower().endswith('.csv'):
            account_type = 'credit' if 'credit' in file.lower() else 'checking'
            path = os.path.join(data_folder, file)
            print(f"\n➡️ Preparing to load: {file} as {account_type}")
            print(f"📁 Full path: {path}")
            print(f"📁 Does file exist? {os.path.exists(path)}")

            try:
                df = load_and_clean_chase_csv(path, account_type)
                print(f"✅ Loaded {len(df)} rows")
                all_dfs.append(df)
            except Exception as e:
                print(f"❌ Failed on {file}: {e}")
                traceback.print_exc()

    if not all_dfs:
        raise ValueError("🚫 No valid data found in any CSVs.")

    return pd.concat(all_dfs).sort_values(by='date').reset_index(drop=True)


if __name__ == "__main__":
    df = load_all_transactions()
    print(df.head(10))  # Print first 10 rows
