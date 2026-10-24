
import json
from pathlib import Path

source = Path("data/starnames.json")
data = json.loads(source.read_text(encoding="utf-8"))

language_fields = {
    "ar", "de", "el", "en", "es", "fa", "fi", "fr",
    "he", "hi", "it", "ja", "ko", "la", "ru", "tr", "zh",
}

def compact(obj):
    return {
        hip: {
            key: value
            for key, value in record.items()
            if value != ""
        } if isinstance(record, dict) else record
        for hip, record in obj.items()
    }

def english_focused(obj):
    return {
        hip: {
            key: value
            for key, value in record.items()
            if key not in language_fields or key == "en"
        } if isinstance(record, dict) else record
        for hip, record in obj.items()
    }

def size(obj):
    return len(json.dumps(
        obj, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8"))

versions = {
    "Original": data,
    "Compact all languages": compact(data),
    "English-focused, compact": compact(english_focused(data)),
}

original_size = size(data)

for label, obj in versions.items():
    current = size(obj)
    print(
        f"{label}: {current:,} bytes | "
        f"saved {original_size-current:,} bytes | "
        f"{(original_size-current)/original_size*100:.1f}% smaller"
    )

print("All record IDs preserved:", all(obj.keys() == data.keys() for obj in versions.values()))
