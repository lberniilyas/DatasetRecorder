"""
Run once to generate scripts.json — the sentences you'll record.

Output: 30 Darija sentences focused on hotel / apartment / trip-planning
vocabulary. Each has Arabic-script transcript (used for training),
Latin-script transliteration (reading aid), and metadata.

Usage:
    pip install -r requirements.txt
    # Set GEMINI_API_KEY in your shell or a .env file in this folder
    python generate_scripts.py

The output `scripts.json` is read by the server at startup.
"""
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google import genai
except ImportError:
    print("ERROR: google-genai not installed. Run `pip install -r requirements.txt`.")
    sys.exit(1)


GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
if not GEMINI_KEY:
    print("ERROR: GEMINI_API_KEY not set. Put it in .env or your shell environment.")
    sys.exit(1)


COUNT = 30
OUTPUT = Path(__file__).parent / "scripts.json"

# Domain breakdown for variety
DISTRIBUTION = {
    "hotel_search": 10,        # finding hotels, filtering by price/stars/location
    "apartment_search": 6,     # apartments / riads / vacation rentals
    "trip_planning": 8,        # full trip requests (X-day, budget, travelers)
    "modification": 4,         # refining a previous request
    "general_travel": 2,       # generic travel Darija (broader coverage)
}

# Length mix (Q7)
LENGTH_MIX = "25% short (2-4 words), 50% medium (5-9 words), 25% long (10-18 words)"


PROMPT = f"""
You are generating training sentences for a Darija (Moroccan Arabic) speech-to-text
model fine-tune. The model will power a Moroccan travel app called BLANI, which
helps users find hotels, apartments, and plan trips.

Generate EXACTLY {COUNT} sentences with this domain distribution:
{json.dumps(DISTRIBUTION, indent=2)}

LENGTH MIX: {LENGTH_MIX}

EACH SENTENCE MUST INCLUDE:
1. arabic — the sentence in Arabic script as a Moroccan would write it on social media
   (NOT formal MSA). Use Darija spelling, not classical Arabic.
   Examples:  بغيت أوتيل رخيص ف فاس
              عافاك شي شقة زوينة ف مراكش قريب من المدينة
              نحتاج بلانينغ ل4 أيام ف الصويرة بـ3000 درهم

2. latin — the SAME sentence written in Latin-script Darija (the way Moroccans text)
   Examples:  bghit otel rkhis f fes
              3afak shi chouqa zwina f marrakech qrib mn lmdina
              n7taj planning l 4 yam f swira b 3000 dh

3. english — natural English translation (for QA verification only — not used for training)

4. length — "short" / "medium" / "long" matching the LENGTH MIX above

5. domain — one of: hotel_search / apartment_search / trip_planning / modification / general_travel

VOCABULARY GUIDANCE (use these terms freely):
- otel / lukanda / فندق = hotel
- chouqa / chqa / شقة = apartment
- riad / ryad / رياض = riad (traditional Moroccan house)
- rkhis / غالي = cheap / expensive
- zwin / mezyan / زوين = nice / good
- lbhar / البحر = the sea
- lmdina / المدينة = the medina / city center
- bghit / كنحتاج = I want / I need
- 3afak / عافاك = please
- yam / nhar / أيام = days
- l'we3kend / weekend / weekend = weekend

USE REAL MOROCCAN CITIES MOSTLY: Fes, Marrakech, Casablanca, Rabat, Agadir,
Tangier, Chefchaouen, Essaouira, Meknes, Ouarzazate, Tetouan, Ifrane

INCLUDE NATURAL CODE-SWITCHING with French words occasionally
("hotel" stays "hotel", "weekend" stays "weekend", "budget" stays "budget").

Return ONLY a JSON array, no markdown, no explanation. Like this:
[
  {{
    "id": "s001",
    "arabic": "بغيت أوتيل رخيص ف فاس",
    "latin": "bghit otel rkhis f fes",
    "english": "I want a cheap hotel in Fes",
    "length": "medium",
    "domain": "hotel_search"
  }},
  ...
]

IDs should be s001 through s{COUNT:03d}.
"""


def generate() -> list[dict]:
    client = genai.Client(api_key=GEMINI_KEY)

    models_to_try = [
        "models/gemini-2.5-flash",
        "models/gemini-2.0-flash",
        "models/gemini-2.0-flash-lite",
    ]

    last_error = None
    for model_name in models_to_try:
        try:
            print(f"Asking {model_name}...")
            response = client.models.generate_content(
                model=model_name, contents=[PROMPT]
            )
            raw = response.text.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError(f"Expected list, got {type(data).__name__}")
            if len(data) == 0:
                raise ValueError("Empty list returned")
            print(f"  → got {len(data)} entries")
            return data
        except Exception as e:
            print(f"  → {model_name} failed: {e}")
            last_error = e
            continue

    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")


def validate(scripts: list[dict]) -> list[dict]:
    """Make sure every entry has required fields and an id."""
    required = ("arabic", "latin", "english", "length", "domain")
    valid = []
    for i, s in enumerate(scripts, 1):
        missing = [k for k in required if not s.get(k)]
        if missing:
            print(f"  ! Entry {i} missing {missing} — skipping")
            continue
        # Ensure id is set
        if not s.get("id"):
            s["id"] = f"s{i:03d}"
        valid.append(s)
    return valid


if __name__ == "__main__":
    scripts = generate()
    scripts = validate(scripts)
    OUTPUT.write_text(
        json.dumps(scripts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✓ Wrote {len(scripts)} scripts to {OUTPUT}")
    print(f"  Domains: {sorted({s['domain'] for s in scripts})}")
    print(f"  Lengths: {sorted({s['length'] for s in scripts})}")
