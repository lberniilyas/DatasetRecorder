"""
BLANI Darija Recorder — Flask server.

Serves the recording webpage and handles:
  POST /api/recordings   → save an audio blob + metadata
  GET  /api/scripts      → return scripts.json + which ids are already recorded
  GET  /api/progress     → recording count

Audio conversion to 16kHz mono WAV is done with ffmpeg (which you have
installed for the BLANI backend). All files end up in ./data/.

Usage:
    pip install -r requirements.txt
    # ensure ffmpeg is on PATH
    python server.py

Then open http://localhost:5050 on your PC, or run `ngrok http 5050`
in another terminal and open the https URL on your iPhone.
"""
import csv
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory


BASE = Path(__file__).parent
DATA = BASE / "data"
AUDIO = DATA / "audio"
CSV_PATH = DATA / "transcripts.csv"
SCRIPTS_PATH = BASE / "scripts.json"

DATA.mkdir(exist_ok=True)
AUDIO.mkdir(exist_ok=True)

CSV_COLUMNS = [
    "id",
    "audio_filename",
    "transcript_arabic",
    "transcript_latin",
    "english",
    "length",
    "domain",
    "speaker_id",
    "duration_seconds",
    "recorded_at",
    "notes",
]


# ────────────────────── CSV helpers

def _ensure_csv():
    if not CSV_PATH.exists():
        with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_COLUMNS).writeheader()


def _load_csv() -> list[dict]:
    _ensure_csv()
    with CSV_PATH.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _save_csv(rows: list[dict]):
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def _upsert(row: dict):
    """Write or replace a row keyed by `id`."""
    rows = _load_csv()
    rows = [r for r in rows if r.get("id") != row["id"]]
    rows.append(row)
    rows.sort(key=lambda r: r["id"])
    _save_csv(rows)


# ────────────────────── Audio conversion

def _convert_to_wav(input_path: Path, output_path: Path) -> float:
    """
    Convert any audio (webm/opus from Chrome, m4a/aac from Safari, wav, mp3…)
    to 16kHz mono WAV. Returns duration in seconds.
    """
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )

    # Probe duration
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return round(float(probe.stdout.strip()), 2)
    except ValueError:
        return 0.0


# ────────────────────── Flask app

app = Flask(__name__, static_folder="static", static_url_path="")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/scripts")
def get_scripts():
    if not SCRIPTS_PATH.exists():
        return jsonify({
            "error": "scripts.json not found — run generate_scripts.py first",
        }), 500

    scripts = json.loads(SCRIPTS_PATH.read_text(encoding="utf-8"))
    recorded_ids = {r["id"] for r in _load_csv()}

    # Annotate each script with its recorded status
    for s in scripts:
        s["recorded"] = s["id"] in recorded_ids

    return jsonify({
        "scripts": scripts,
        "total": len(scripts),
        "recorded_count": len(recorded_ids),
    })


@app.get("/api/progress")
def get_progress():
    recorded_ids = sorted({r["id"] for r in _load_csv()})
    return jsonify({"recorded_count": len(recorded_ids), "recorded_ids": recorded_ids})


@app.post("/api/recordings")
def post_recording():
    """
    Multipart form:
      audio        (file)
      id           — script id, e.g. "s001"
      speaker_id   — e.g. "ilyas"
      notes        — optional free text
    Metadata for the row is looked up from scripts.json by id.
    """
    audio = request.files.get("audio")
    script_id = (request.form.get("id") or "").strip()
    speaker_id = (request.form.get("speaker_id") or "anonymous").strip()
    notes = (request.form.get("notes") or "").strip()

    if not audio or not script_id:
        return jsonify({"error": "audio and id are required"}), 400

    # Look up the script's metadata
    scripts = json.loads(SCRIPTS_PATH.read_text(encoding="utf-8"))
    script = next((s for s in scripts if s.get("id") == script_id), None)
    if not script:
        return jsonify({"error": f"unknown script id {script_id}"}), 404

    # Save the upload to a temp file first
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=f"_{script_id}", dir=str(AUDIO)
    ) as tmp:
        audio.save(tmp.name)
        tmp_path = Path(tmp.name)

    out_filename = f"{script_id}_{speaker_id}.wav"
    out_path = AUDIO / out_filename

    try:
        duration = _convert_to_wav(tmp_path, out_path)
    except subprocess.CalledProcessError as e:
        return jsonify({
            "error": "ffmpeg conversion failed",
            "stderr": e.stderr.decode("utf-8", errors="ignore")[:500],
        }), 500
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    row = {
        "id": script_id,
        "audio_filename": out_filename,
        "transcript_arabic": script.get("arabic", ""),
        "transcript_latin": script.get("latin", ""),
        "english": script.get("english", ""),
        "length": script.get("length", ""),
        "domain": script.get("domain", ""),
        "speaker_id": speaker_id,
        "duration_seconds": duration,
        "recorded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "notes": notes,
    }
    _upsert(row)

    return jsonify({"ok": True, "row": row})


@app.delete("/api/recordings/<script_id>")
def delete_recording(script_id):
    """Remove a recording so it can be redone fresh."""
    rows = _load_csv()
    row = next((r for r in rows if r.get("id") == script_id), None)
    if row:
        try:
            (AUDIO / row["audio_filename"]).unlink(missing_ok=True)
        except OSError:
            pass
    rows = [r for r in rows if r.get("id") != script_id]
    _save_csv(rows)
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("BLANI Darija Recorder")
    print(f"  data dir: {DATA}")
    print(f"  scripts:  {'OK' if SCRIPTS_PATH.exists() else 'MISSING — run generate_scripts.py first'}")
    print(f"  open:     http://localhost:5050")
    print(f"  ngrok:    ngrok http 5050   (for iPhone access)")
    app.run(host="0.0.0.0", port=5050, debug=False)
