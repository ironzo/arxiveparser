import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
uid = os.getenv("UID")

def tg_notify(text: str, chat_id: str = None) -> None:
    """Send a single message to Telegram"""
    # Use provided chat_id or fall back to default UID
    target_chat_id = chat_id if chat_id is not None else uid
    print(f"Sending to chat_id: {target_chat_id}")
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            timeout=10,  # Increased timeout for reliability
            data={"chat_id": target_chat_id, "text": text, "parse_mode": "Markdown"},
        )
    except Exception as exc:
        print("Telegram notify failed: %s", exc)

def tg_notify_multiple(text: str, max_length: int = 4000, chat_id: str = None) -> None:
    """Send multiple messages if text is too long for Telegram"""
    # Use provided chat_id or fall back to default UID
    target_chat_id = chat_id if chat_id is not None else uid
    print(f"Sending to chat_id: {target_chat_id}")
    
    # Split text into chunks that fit within Telegram's limit
    chunks = []
    current_chunk = ""
    
    # Split by paragraphs first
    paragraphs = text.split('\n\n')
    
    for paragraph in paragraphs:
        # If adding this paragraph would exceed limit, save current chunk and start new one
        if len(current_chunk) + len(paragraph) + 2 > max_length:  # +2 for \n\n
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = paragraph
            else:
                # If single paragraph is too long, split it by sentences
                sentences = paragraph.split('. ')
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 2 > max_length:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = sentence
                        else:
                            # If single sentence is too long, force split
                            chunks.append(sentence[:max_length])
                            current_chunk = sentence[max_length:]
                    else:
                        current_chunk += sentence + ". "
        else:
            current_chunk += paragraph + "\n\n"
    
    # Add the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # Send each chunk
    for i, chunk in enumerate(chunks):
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                timeout=10,  # Increased timeout for reliability
                data={"chat_id": target_chat_id, "text": chunk, "parse_mode": "Markdown"},
            )
            print(f"Sent message part {i+1}/{len(chunks)}")
        except Exception as exc:
            print(f"Telegram notify failed for part {i+1}: %s", exc)