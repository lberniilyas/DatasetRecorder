# BLANI Darija Recorder

A small mobile-first web tool to record Darija audio for fine-tuning
your Whisper-Darija model. You see a sentence, tap record, speak, tap
stop, save. Audio + transcript metadata get written to disk as a
HuggingFace-ready dataset.

## What you'll need

- Python 3.10+
- `ffmpeg` installed and on your PATH
  (you already have it from the BLANI backend work)
- A `GEMINI_API_KEY` (only used **once**, to generate the script list)
- An **ngrok** free account, if you want to record from your iPhone

## Setup

```bash
# from this folder
pip install -r requirements.txt
cp .env.example .env
# edit .env, paste your GEMINI_API_KEY
```

## Step 1 — Generate the script list

This calls Gemini once to produce 30 Darija sentences (focused on
hotels, apartments, and trip planning per your scope), in Arabic
script + Latin transliteration + English translation. Writes
`scripts.json` in the same folder.

```bash
python generate_scripts.py
```

You can re-run this any time to refresh the script set. The server
reads `scripts.json` on every request, so changes are picked up live.

**Review `scripts.json` before recording.** If any sentence looks
weird or wrong, edit the file by hand — the file is plain JSON.

## Step 2 — Start the server

```bash
python server.py
```

You'll see:
```
  open:     http://localhost:5050
  ngrok:    ngrok http 5050   (for iPhone access)
```

Open `http://localhost:5050` in your browser to test on your PC.
Allow microphone access when prompted.

## Step 3 — Record from your iPhone (HTTPS via ngrok)

iPhone Safari requires HTTPS to use the microphone. `localhost`
doesn't qualify — you need a public HTTPS URL pointing at your PC.
ngrok provides this for free.

1. Sign up at https://ngrok.com (free tier is fine)
2. Install ngrok, run `ngrok config add-authtoken <your-token>` once
3. In a **second terminal**, while `server.py` is running:
   ```bash
   ngrok http 5050
   ```
4. ngrok prints something like `Forwarding https://abc123.ngrok-free.app -> http://localhost:5050`
5. On your iPhone, open Safari and go to `https://abc123.ngrok-free.app`
6. Safari will ask for microphone permission. Allow it.
7. (Optional) **Add to Home Screen** from the Share menu — gives you an
   app-style icon on your phone.

Your recordings still save to the PC running `server.py` — the iPhone
is just the better microphone.

## Recording workflow

1. Type your **speaker name** in the box (it's saved between sessions).
2. Tap **Hold to Record** — the dot turns orange, the timer starts.
3. Read the sentence (Arabic script preferred; Latin shown below as a guide).
4. Tap the button again to stop.
5. The audio playback widget appears. Listen back. If it sounds clean:
   - Tap **Save & Next** → moves to the next un-recorded script.
6. If it sounds bad:
   - Tap **Re-record** → records over the same script.
7. Want to skip a sentence you can't read?
   - Tap **Skip** → jumps to the next un-recorded one.

Use the bottom nav (← / Jump to… / →) to revisit anything.

## Where data ends up

```
data/
├── audio/
│   ├── s001_ilyas.wav     # 16kHz mono PCM WAV
│   ├── s002_ilyas.wav
│   └── ...
└── transcripts.csv        # one row per recording
```

`transcripts.csv` columns:
- `id` — script id (s001, s002, …)
- `audio_filename`
- `transcript_arabic` — what the model will be trained to output
- `transcript_latin` — for QA / reference
- `english` — for QA only
- `length` — short/medium/long
- `domain` — hotel_search / apartment_search / trip_planning / modification / general_travel
- `speaker_id`
- `duration_seconds`
- `recorded_at`
- `notes`

## Tips for clean recordings

- Quiet room. Close window, no fans, no nearby conversation.
- iPhone 6–12 inches from your mouth.
- Don't pop into the mic. Soft breath before/after each phrase.
- Re-record without shame — bad samples poison the model.
- If you find yourself stumbling on a sentence repeatedly, **Skip** it
  and move on. Fluent reads are worth more than struggle reads.
- One sitting per session, ~20-30 minutes. Voice fatigue shows up
  in the audio and hurts the model.

## Re-doing a recording later

The server stores at most **one recording per script id per speaker**.
Re-recording overwrites the old file and CSV row. So if you find a
bad take later, just navigate back to that script (use Jump to…) and
record again.

## Building the dataset for HuggingFace

When you have your batch of recordings, the `transcripts.csv` is
already in a compatible shape. Loading into `datasets`:

```python
from datasets import load_dataset, Audio
ds = load_dataset(
    "csv",
    data_files="data/transcripts.csv",
    split="train",
)
ds = ds.cast_column("audio_filename", Audio(sampling_rate=16_000))
# (rename columns as needed for your Whisper training script)
```

When we move to actual fine-tuning, we'll write a small loader that
joins `audio/` and `transcripts.csv` properly. For now, just collect
the data.

## Troubleshooting

**"Mic error" on the page** — Browser denied microphone access.
On Chrome/Edge: click the lock icon in the address bar → allow mic.
On iPhone Safari: Settings → Safari → Camera & Microphone → Allow.

**"ffmpeg conversion failed"** — `ffmpeg` not on PATH, or audio blob
arrived corrupted. Confirm `ffmpeg -version` works in the same shell
you ran `python server.py` from.

**"scripts.json not found"** — You skipped Step 1. Run
`python generate_scripts.py` first.

**Audio sounds quiet/distorted** — Move closer to the mic, check your
input gain in the OS settings. On Windows: Settings → System → Sound
→ Input → Test your microphone.

**iPhone can't connect to ngrok URL** — Make sure ngrok is actually
running (`ngrok http 5050` in a separate terminal). Free-tier URLs
change every restart, so re-copy the URL each time.
