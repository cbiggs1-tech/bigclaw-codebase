#!/usr/bin/env python3
"""Gmail checker for BigClaw — uses IMAP + App Password (no OAuth expiry).

Usage:
    python3 gmail_check.py                  # Check for important unread
    python3 gmail_check.py --unread         # All unread
    python3 gmail_check.py --spam-audit     # Audit subscription/spam senders
    python3 gmail_check.py --limit N        # Limit results
"""

import argparse
import imaplib
import email
import re
import os
from email.header import decode_header
from datetime import datetime

# Config
GMAIL_USER     = "cbiggs1@gmail.com"
GMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")  # strip spaces
IMAP_HOST      = "imap.gmail.com"
IMAP_PORT      = 993

# Classification rules
IMPORTANT_SENDERS = [
    'alpaca', 'schwab', 'fidelity', 'vanguard', 'bank', 'chase', 'wellsfargo',
    'irs', '.gov', 'court', 'attorney', 'doctor', 'medical', 'hospital',
    'school', 'payroll', 'salary', 'insurance', 'mortgage', 'title',
]

JUNK_PATTERNS = [
    'noreply', 'no-reply', 'marketing', 'promo', 'newsletter',
    'deals', 'offer', 'sale', 'discount', 'coupon',
    'unsubscribe', 'notifications@', 'news@', 'hello@', 'info@',
]


def decode_str(s):
    """Decode encoded email header string."""
    if s is None:
        return ""
    parts = decode_header(s)
    result = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def connect():
    """Connect to Gmail IMAP."""
    if not GMAIL_PASSWORD:
        raise ValueError("GMAIL_APP_PASSWORD not set in environment")
    imaplib._MAXLINE = 10_000_000  # 10MB — needed for large inboxes
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(GMAIL_USER, GMAIL_PASSWORD)
    return mail


def fetch_unread(mail, folder="INBOX", exclude_categories=True, limit=30):
    """Fetch unread messages from Gmail."""
    mail.select(folder)

    # Search unread from last 24 hours only (ignore the 200K backlog)
    from datetime import timedelta
    since_date = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
    status, data = mail.search(None, f'UNSEEN SINCE {since_date}')
    if status != "OK":
        return []

    ids = data[0].split()
    if not ids:
        return []

    # Most recent first
    ids = ids[-limit:][::-1]

    messages = []
    for uid in ids:
        status, msg_data = mail.fetch(uid, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE LIST-UNSUBSCRIBE)])')
        if status != "OK":
            continue

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        from_addr = decode_str(msg.get("From", ""))
        subject   = decode_str(msg.get("Subject", "(no subject)"))
        date      = msg.get("Date", "")
        unsub     = msg.get("List-Unsubscribe", "")

        from_lower = from_addr.lower()
        is_important = any(s in from_lower for s in IMPORTANT_SENDERS)
        is_junk = any(p in from_lower for p in JUNK_PATTERNS) or bool(unsub)

        # Override: if important sender, not junk
        if is_important:
            is_junk = False

        messages.append({
            "id": uid,
            "from": from_addr,
            "subject": subject,
            "date": date,
            "unsubscribe": unsub,
            "is_important": is_important,
            "is_junk": is_junk,
        })

    return messages


def audit_spam(mail, limit=100):
    """Count senders in recent inbox."""
    mail.select("INBOX")
    status, data = mail.search(None, 'ALL')
    if status != "OK":
        return [], {}

    ids = data[0].split()[-limit:][::-1]
    sender_counts = {}
    sender_unsub = {}

    for uid in ids:
        status, msg_data = mail.fetch(uid, '(BODY.PEEK[HEADER.FIELDS (FROM LIST-UNSUBSCRIBE)])')
        if status != "OK":
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        from_addr = decode_str(msg.get("From", "Unknown"))
        unsub = msg.get("List-Unsubscribe", "")
        sender_counts[from_addr] = sender_counts.get(from_addr, 0) + 1
        if unsub:
            sender_unsub[from_addr] = unsub

    sorted_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)
    return sorted_senders, sender_unsub


def format_inbox(messages):
    important = [m for m in messages if m["is_important"]]
    regular   = [m for m in messages if not m["is_important"] and not m["is_junk"]]
    junk      = [m for m in messages if m["is_junk"]]

    lines = []

    if not messages:
        lines.append("✅ No unread messages!")
        return "\n".join(lines)

    lines.append(f"📬 Gmail — {len(messages)} unread\n")

    if important:
        lines.append(f"🔴 Important ({len(important)}):")
        for m in important:
            lines.append(f"  📧 {m['from'][:55]}")
            lines.append(f"     {m['subject'][:70]}")

    if regular:
        lines.append(f"\n📨 Other ({len(regular)}):")
        for m in regular[:8]:
            lines.append(f"  {m['from'][:40]} — {m['subject'][:50]}")

    if junk:
        lines.append(f"\n🗑️ Promotional/Junk ({len(junk)}):")
        for m in junk[:5]:
            lines.append(f"  {m['from'][:40]} — {m['subject'][:50]}")
        if len(junk) > 5:
            lines.append(f"  ...and {len(junk) - 5} more")

    return "\n".join(lines)


def format_spam_audit(sorted_senders, sender_unsub):
    lines = ["📊 Gmail Spam Audit — Top Senders\n"]
    for sender, count in sorted_senders[:25]:
        has_unsub = "🔗" if sender in sender_unsub else "  "
        lines.append(f"  {has_unsub} {count:3d}x — {sender[:60]}")
    lines.append(f"\n🔗 = has unsubscribe link | Total senders: {len(sorted_senders)}")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gmail checker (IMAP)")
    parser.add_argument("--unread",     action="store_true", help="All unread")
    parser.add_argument("--spam-audit", action="store_true", help="Audit spam")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    try:
        mail = connect()

        if args.spam_audit:
            sorted_senders, sender_unsub = audit_spam(mail, args.limit)
            print(format_spam_audit(sorted_senders, sender_unsub))
        else:
            messages = fetch_unread(mail, limit=args.limit)
            print(format_inbox(messages))

        mail.logout()

    except Exception as e:
        print(f"❌ Gmail error: {e}")
        import traceback
        traceback.print_exc()
