import os
import json
import requests
import subprocess
import argparse
from datetime import datetime
import yfinance as yf

# Load env
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.expanduser('~/.env_secrets'))

X_BEARER_TOKEN = os.getenv('X_BEARER_TOKEN')
if not X_BEARER_TOKEN:
    raise ValueError("X_BEARER_TOKEN not set in ~/.env_secrets")

CACHE_DIR = os.path.expanduser('~/bigclaw-ai/data/')
LAST_SENTIMENT = os.path.join(CACHE_DIR, 'last_sentiment.json')
HEARTBEAT_STATE = os.path.join(CACHE_DIR, 'heartbeat-state.json')

def fetch_x_tweets(query, count=100):
    url = "https://api.twitter.com/2/tweets/search/recent"
    params = {'query': query, 'max_results': count}
    headers = {'Authorization': f'Bearer {X_BEARER_TOKEN}'}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json().get('data', [])

def run_sentiment(tickers):
    cmd = ['python3', os.path.expanduser('~/bigclaw-ai/src/sentiment.py')] + tickers.split(',')
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout  # Assume it outputs JSON or parseable

def get_price_change(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period='1d')
    if not hist.empty:
        return (hist['Close'][-1] - hist['Open'][0]) / hist['Open'][0] * 100
    return 0

def load_cache(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    return {}

def save_cache(file_path, data):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(data, f)

def send_slack_alert(message):
    # Placeholder: Use message tool or curl to Slack webhook if configured
    print(f"ALERT: {message}")  # For now, just print; integrate properly

def main(args):
    config = load_cache(os.path.expanduser('~/.openclaw/workspace/skills/realtime-x-sentiment-tracker/references/config.json'))
    tickers = args.tickers or config.get('tickers', 'TSLA,NVDA,PLTR')
    threshold_sentiment = config.get('threshold_sentiment', 5)
    threshold_price = config.get('threshold_price', 3)

    last_sent = load_cache(LAST_SENTIMENT)
    current_sent = json.loads(run_sentiment(tickers))  # Assume dict {ticker: score}

    alerts = []
    for ticker in tickers.split(','):
        prev = last_sent.get(ticker, 0)
        curr = current_sent.get(ticker, 0)
        shift = abs(curr - prev)
        price_change = get_price_change(ticker)

        if shift > threshold_sentiment or abs(price_change) > threshold_price:
            alerts.append(f"{ticker}: Sentiment shift {shift}% ({prev}→{curr}), Price {price_change:.1f}%")

    if alerts:
        send_slack_alert('\n'.join(alerts))

    save_cache(LAST_SENTIMENT, current_sent)
    state = load_cache(HEARTBEAT_STATE)
    state['last_poll'] = datetime.now().isoformat()
    save_cache(HEARTBEAT_STATE, state)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tickers', default='TSLA,NVDA')
    parser.add_argument('--interval', type=int, default=7200)  # Not used here, for cron
    args = parser.parse_args()
    main(args)
