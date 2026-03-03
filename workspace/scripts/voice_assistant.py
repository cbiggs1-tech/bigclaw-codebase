#!/usr/bin/env python3
"""BigClaw Voice Assistant — listen, think, speak loop.

Usage:
    source ~/.env_secrets
    python3 voice_assistant.py                  # Normal mode
    python3 voice_assistant.py --wake-word      # Only respond to "hey bigclaw"
    python3 voice_assistant.py --listen-sec 6   # Adjust listen duration
    python3 voice_assistant.py --once           # Single exchange then exit

Requires:
    ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ANTHROPIC_API_KEY in env
"""

import argparse
import io
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import requests

# Config
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

MIC_DEVICE = "hw:3,0"        # Fallback ALSA
SPEAKER_DEVICE = "hw:0,0"    # Fallback ALSA
USE_PIPEWIRE = True           # Use PipeWire for Bluetooth audio
SAMPLE_RATE = 16000
LISTEN_SECONDS = 6
MAX_RESPONSE_CHARS = 300  # Keep TTS responses short to avoid timeout

SYSTEM_PROMPT = """You are BigClaw, a friendly and sharp AI assistant running on a Raspberry Pi. 
You're talking to Curtis via voice. Keep responses SHORT and conversational — under 2-3 sentences.
You're an investment research agent but also a general assistant.
Be natural, like talking to a friend. Don't use markdown or formatting — this is spoken aloud.
If asked about markets or stocks, give brief verbal summaries.
Never say "as an AI" — you're BigClaw."""

conversation_history = []


def speak(text, max_len=MAX_RESPONSE_CHARS):
    """Generate TTS and play through speakers."""
    # Truncate if too long
    if len(text) > max_len:
        # Find a good break point
        text = text[:max_len]
        last_period = text.rfind('.')
        last_question = text.rfind('?')
        last_exclaim = text.rfind('!')
        break_point = max(last_period, last_question, last_exclaim)
        if break_point > 100:
            text = text[:break_point + 1]
    
    print(f"  🗣️  {text}")
    
    try:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "model_id": "eleven_monolingual_v1",
            },
            timeout=15,
        )
        
        if resp.status_code != 200:
            print(f"  ⚠️  TTS error: HTTP {resp.status_code}")
            return
        
        # Save MP3, convert to WAV, play
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(resp.content)
            mp3_path = f.name
        
        wav_path = mp3_path.replace(".mp3", ".wav")
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path, "-ar", "44100", "-ac", "1", wav_path],
            capture_output=True, timeout=10,
        )
        if USE_PIPEWIRE:
            subprocess.run(
                ["pw-play", wav_path],
                capture_output=True, timeout=30,
            )
        else:
            subprocess.run(
                ["aplay", "-D", SPEAKER_DEVICE, wav_path],
                capture_output=True, timeout=30,
            )
        
        # Cleanup
        os.unlink(mp3_path)
        os.unlink(wav_path)
        
    except Exception as e:
        print(f"  ⚠️  Speak error: {e}")


def listen(seconds=LISTEN_SECONDS):
    """Record from mic and return audio file path."""
    wav_path = tempfile.mktemp(suffix=".wav")
    
    print(f"  👂 Listening for {seconds}s...")
    
    try:
        if USE_PIPEWIRE:
            # Use pw-record for Bluetooth mic support
            proc = subprocess.Popen(
                ["pw-record", wav_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            time.sleep(seconds)
            proc.terminate()
            proc.wait(timeout=3)
        else:
            result = subprocess.run(
                ["arecord", "-D", MIC_DEVICE, "-f", "S16_LE", "-r", str(SAMPLE_RATE),
                 "-c", "1", "-d", str(seconds), wav_path],
                capture_output=True, timeout=seconds + 5,
            )
            if result.returncode != 0:
                print(f"  ⚠️  Record error: {result.stderr.decode()[:100]}")
                return None
        
        if os.path.exists(wav_path) and os.path.getsize(wav_path) > 1000:
            return wav_path
        else:
            print("  ⚠️  Recording too small or missing")
            return None
    except Exception as e:
        print(f"  ⚠️  Listen error: {e}")
        return None


def transcribe(wav_path):
    """Transcribe audio using ElevenLabs STT."""
    try:
        with open(wav_path, "rb") as f:
            resp = requests.post(
                "https://api.elevenlabs.io/v1/speech-to-text",
                headers={"xi-api-key": ELEVENLABS_API_KEY},
                files={"file": ("audio.wav", f, "audio/wav")},
                data={"model_id": "scribe_v1"},
                timeout=20,
            )
        
        if resp.status_code != 200:
            print(f"  ⚠️  STT error: HTTP {resp.status_code}")
            return ""
        
        data = resp.json()
        text = data.get("text", "").strip()
        return text
    except Exception as e:
        print(f"  ⚠️  Transcribe error: {e}")
        return ""
    finally:
        try:
            os.unlink(wav_path)
        except:
            pass


def think(user_text):
    """Generate response using Anthropic Claude."""
    global conversation_history
    
    conversation_history.append({"role": "user", "content": user_text})
    
    # Keep history manageable
    if len(conversation_history) > 20:
        conversation_history = conversation_history[-20:]
    
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 200,
                "system": SYSTEM_PROMPT,
                "messages": conversation_history,
            },
            timeout=30,
        )
        
        if resp.status_code != 200:
            print(f"  ⚠️  Think error: HTTP {resp.status_code} {resp.text[:200]}")
            return "Sorry, I had trouble thinking about that. Try again?"
        
        data = resp.json()
        response = data["content"][0]["text"]
        
        conversation_history.append({"role": "assistant", "content": response})
        
        return response
    except Exception as e:
        print(f"  ⚠️  Think error: {e}")
        return "Sorry, I hit a snag. Try again?"


def is_silence(wav_path, threshold=500):
    """Check if audio is mostly silence (no speech detected)."""
    try:
        result = subprocess.run(
            ["sox", wav_path, "-n", "stat"],
            capture_output=True, timeout=5,
        )
        # Parse RMS amplitude from sox stat
        stderr = result.stderr.decode()
        for line in stderr.split('\n'):
            if 'RMS' in line and 'amplitude' in line:
                rms = float(line.split()[-1])
                return rms < 0.001  # Only skip true silence
        return False
    except:
        return False


def is_exit_command(text):
    """Check if user wants to stop. Only exact/near-exact matches."""
    exit_phrases = [
        "goodbye bigclaw", "goodbye big claw", "bye bigclaw", 
        "stop listening", "quit listening", "exit voice",
        "go to sleep", "stop voice assistant",
    ]
    text_lower = text.lower().strip()
    # Must be a close match, not just a substring
    return any(phrase in text_lower for phrase in exit_phrases)


def is_wake_word(text):
    """Check for wake word."""
    wake_phrases = ["hey bigclaw", "hey big claw", "bigclaw", "big claw", "hey claw"]
    text_lower = text.lower().strip()
    return any(phrase in text_lower for phrase in wake_phrases)


def main():
    parser = argparse.ArgumentParser(description="BigClaw Voice Assistant")
    parser.add_argument("--wake-word", action="store_true", help="Require wake word")
    parser.add_argument("--listen-sec", type=int, default=LISTEN_SECONDS, help="Listen duration")
    parser.add_argument("--once", action="store_true", help="Single exchange")
    parser.add_argument("--max-chars", type=int, default=MAX_RESPONSE_CHARS, help="Max response chars")
    args = parser.parse_args()
    
    listen_sec = args.listen_sec
    max_chars = args.max_chars
    
    # Validate keys
    if not all([ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ANTHROPIC_API_KEY]):
        print("❌ Missing API keys. Source ~/.env_secrets first.")
        sys.exit(1)
    
    print("🦀 BigClaw Voice Assistant starting...")
    print(f"   Listen: {listen_sec}s | Max response: {max_chars} chars")
    print(f"   Wake word: {'ON' if args.wake_word else 'OFF'}")
    print(f"   Say 'goodbye' or 'stop' to exit.\n")
    
    # Greeting
    speak("BigClaw voice assistant is ready. Go ahead, I'm listening.")
    
    while True:
        try:
            # Listen
            wav_path = listen(listen_sec)
            if not wav_path:
                continue
            
            # Check for silence (use sox RMS, very low threshold)
            if is_silence(wav_path):
                print("  (silence, skipping)")
                try:
                    os.unlink(wav_path)
                except:
                    pass
                continue
            
            # Transcribe
            text = transcribe(wav_path)
            
            if not text or len(text.strip()) < 2:
                print("  (no speech detected)")
                continue
            
            print(f"  👤 Curtis: {text}")
            
            # Wake word check
            if args.wake_word and not is_wake_word(text):
                print("  (no wake word, ignoring)")
                continue
            
            # Strip wake word from text
            for phrase in ["hey bigclaw", "hey big claw", "bigclaw", "big claw"]:
                text = re.sub(phrase, "", text, flags=re.IGNORECASE).strip()
                text = text.lstrip(",").lstrip(".").strip()
            
            if not text:
                speak("Yeah? What's up?")
                continue
            
            # Exit check
            if is_exit_command(text):
                speak("Later Curtis. I'll be here when you need me.")
                break
            
            # Think and respond
            response = think(text)
            speak(response)
            
            if args.once:
                break
                
        except KeyboardInterrupt:
            print("\n\n🦀 Voice assistant stopped.")
            break
        except Exception as e:
            print(f"  ⚠️  Loop error: {e}")
            time.sleep(1)
    
    print("\n🦀 BigClaw voice assistant stopped.")


if __name__ == "__main__":
    main()
