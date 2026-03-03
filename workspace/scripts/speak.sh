#!/bin/bash
# BigClaw ElevenLabs TTS — always use this, never built-in tts tool
# Usage: speak.sh "text to speak" [output_path]
source ~/.env_secrets
TEXT="$1"
OUT="${2:-/tmp/bigclaw_speech.mp3}"
curl -s "https://api.elevenlabs.io/v1/text-to-speech/$ELEVENLABS_VOICE_ID" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"text\":$(echo "$TEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),\"model_id\":\"eleven_monolingual_v1\"}" \
  -o "$OUT"
echo "$OUT"
