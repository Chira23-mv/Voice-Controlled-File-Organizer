"""
Voice-Controlled File Organizer (with Undo)
-------------------------------------------
Say things like:
  "move all pdfs to documents"
  "move images from desktop to pictures"
  "clean my downloads folder"
  "undo"      "show history"      "quit"

Run:   python 3_voice_file_organizer.py           (microphone)
       python 3_voice_file_organizer.py --text    (type commands instead)

Install:  pip install SpeechRecognition pyaudio
(Speech recognition uses Google's free web API, so it needs internet. --text mode needs nothing.)
"""
import json
import re
import shutil
import sys
from pathlib import Path

HOME = Path.home()
HISTORY_FILE = HOME / ".voice_organizer_history.json"

FOLDERS = {
    "downloads": HOME / "Downloads", "documents": HOME / "Documents",
    "desktop": HOME / "Desktop", "pictures": HOME / "Pictures",
    "videos": HOME / "Videos", "music": HOME / "Music",
}

TYPES = {
    "pdf": [".pdf"],
    "image": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
    "photo": [".jpg", ".jpeg", ".png", ".heic"],
    "picture": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
    "video": [".mp4", ".mkv", ".mov", ".avi", ".webm"],
    "music": [".mp3", ".wav", ".flac", ".m4a"],
    "audio": [".mp3", ".wav", ".flac", ".m4a"],
    "song": [".mp3", ".wav", ".flac", ".m4a"],
    "document": [".doc", ".docx", ".txt", ".odt", ".rtf", ".pdf"],
    "doc": [".doc", ".docx"],
    "spreadsheet": [".xls", ".xlsx", ".csv"],
    "presentation": [".ppt", ".pptx"],
    "zip": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "archive": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "code": [".py", ".js", ".java", ".cpp", ".c", ".html", ".css"],
}

# For "clean my downloads folder": extension -> subfolder name
CLEAN_MAP = {}
for label, sub in [("image", "Images"), ("video", "Videos"), ("music", "Music"), ("doc", "Documents"),
                   ("pdf", "PDFs"), ("spreadsheet", "Spreadsheets"), ("presentation", "Presentations"),
                   ("zip", "Archives"), ("code", "Code")]:
    for ext in TYPES[label]:
        CLEAN_MAP[ext] = sub


# ---------------------------------------------------------------- history
def load_history() -> list:
    try:
        return json.loads(HISTORY_FILE.read_text())
    except Exception:
        return []


def save_history(history: list) -> None:
    HISTORY_FILE.write_text(json.dumps(history[-50:], indent=2))


# ---------------------------------------------------------------- file ops
def resolve_folder(name: str) -> Path:
    key = name.lower().strip()
    return FOLDERS.get(key, HOME / key.capitalize())


def safe_move(src: Path, dest_dir: Path) -> Path:
    """Move without overwriting: report (1), (2)... on name clashes."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / src.name
    n = 1
    while target.exists():
        target = dest_dir / f"{src.stem} ({n}){src.suffix}"
        n += 1
    shutil.move(str(src), str(target))
    return target


def lookup_type(word: str):
    w = word.lower()
    if w in TYPES:
        return w
    if w.endswith("s") and w[:-1] in TYPES:
        return w[:-1]
    return None


# ---------------------------------------------------------------- commands
def cmd_move(kind: str, source: Path, dest: Path) -> str:
    exts = TYPES[kind]
    files = [p for p in source.glob("*") if p.is_file() and p.suffix.lower() in exts]
    if not files:
        return f"No {kind} files found in {source.name}."
    batch = [{"from": str(f), "to": str(safe_move(f, dest))} for f in files]
    history = load_history()
    history.append({"action": f"move {kind}s {source.name} -> {dest.name}", "moves": batch})
    save_history(history)
    return f"✅ Moved {len(batch)} file(s) to {dest}."


def cmd_clean(source: Path) -> str:
    batch = []
    for f in [p for p in source.glob("*") if p.is_file()]:
        sub = CLEAN_MAP.get(f.suffix.lower())
        if sub:
            batch.append({"from": str(f), "to": str(safe_move(f, source / sub))})
    if not batch:
        return f"{source.name} is already tidy."
    history = load_history()
    history.append({"action": f"clean {source.name}", "moves": batch})
    save_history(history)
    return f"✅ Organized {len(batch)} file(s) into subfolders inside {source}."


def cmd_undo() -> str:
    history = load_history()
    if not history:
        return "Nothing to undo."
    last = history.pop()
    restored = 0
    for m in reversed(last["moves"]):
        src, original = Path(m["to"]), Path(m["from"])
        if src.exists():
            safe_move(src, original.parent)
            restored += 1
    save_history(history)
    return f"↩️ Undid '{last['action']}' ({restored} file(s) restored)."


def cmd_history() -> str:
    history = load_history()
    if not history:
        return "History is empty."
    return "\n".join(f"  {i + 1}. {h['action']} ({len(h['moves'])} files)" for i, h in enumerate(history[-10:]))


def handle(text: str) -> str:
    t = text.lower().strip()

    if re.search(r"\bundo\b|\bwhoops\b|\brevert\b", t):
        return cmd_undo()
    if "history" in t:
        return cmd_history()

    m = re.search(r"(clean|organi[sz]e|sort|tidy)\b.*?\b(downloads|desktop|documents)", t)
    if m:
        return cmd_clean(resolve_folder(m.group(2)))

    m = re.search(r"move (?:all )?(?:my )?(\w+?)(?: files)?(?: from (\w+))? to (?:my )?(\w+)", t)
    if m:
        kind = lookup_type(m.group(1))
        if not kind:
            return f"I don't know the file type '{m.group(1)}'."
        source = resolve_folder(m.group(2) or "downloads")
        if not source.exists():
            return f"Folder {source} doesn't exist."
        return cmd_move(kind, source, resolve_folder(m.group(3)))

    return "🤔 I didn't get that. Try: 'move all pdfs to documents' or 'clean my downloads folder'."


# ---------------------------------------------------------------- input
def listen() -> str:
    import speech_recognition as sr
    r = sr.Recognizer()
    with sr.Microphone() as mic:
        r.adjust_for_ambient_noise(mic, duration=0.5)
        print("🎤 Listening...")
        audio = r.listen(mic, timeout=8, phrase_time_limit=8)
    return r.recognize_google(audio)


def main() -> None:
    use_voice = "--text" not in sys.argv
    if use_voice:
        try:
            import speech_recognition  # noqa: F401
        except ImportError:
            print("SpeechRecognition not installed, falling back to text mode.")
            use_voice = False

    print("🗂️  Voice File Organizer. Say/type 'quit' to exit.")
    while True:
        try:
            text = listen() if use_voice else input("\n> ")
            print(f"You said: {text}")
        except KeyboardInterrupt:
            break
        except Exception as e:  # no mic, silence, unintelligible audio, no internet
            print(f"⚠️  Couldn't capture voice ({type(e).__name__}). Switching to typing.")
            use_voice = False
            continue
        if text.lower().strip() in {"quit", "exit", "stop", "bye"}:
            break
        print(handle(text))
    print("Bye 👋")


if __name__ == "__main__":
    main()
