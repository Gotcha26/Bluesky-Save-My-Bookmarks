**English** | [Français](README.md)

# BSMB - Bsky Save My Bookmarks

Automatically save the images, videos and texts of your Bluesky bookmarks.

> The French [README](README.md) is the reference; this page is its English translation. The
> technical guides ([ADVANCED.md](ADVANCED.md) and the others) are only available in French.

---

## How does it work?

1. You connect your Bluesky account (once)
2. BSMB fetches the list of your bookmarks
3. It downloads the media (images, videos, texts) into a local folder
4. On every run, only the **new** bookmarks are processed

Everything is automatic. No token to copy and paste, no file to edit by hand.

---

## Installation

### Windows

1. Download the project (green **Code** button > **Download ZIP**)
2. Unzip the folder
3. Double-click `Start.bat`

The script automatically installs Python (through `winget`, or Chocolatey as a fallback), ffmpeg and exiftool if needed, creates a `.venv` virtual environment, then starts BSMB. If Python has just been installed, close the window and run `Start.bat` again.

### Linux / macOS

```bash
git clone https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks.git
cd Bluesky-Save-My-Bookmarks
./start.sh
```

The script creates `.venv`, installs the dependencies and checks that ffmpeg and exiftool are present (both optional, used for metadata): `sudo apt install ffmpeg libimage-exiftool-perl` or `brew install ffmpeg exiftool`.

### Alternative: pipx

```bash
pipx install .
bsmb
```

BSMB reads and writes `config.json`, `bsmb.db` and `logs/` in its installation folder (the one containing `bsmb.py`), whatever the current folder. **With pipx, this folder lives inside the pipx environment: these files (credentials, history, logs) are lost on `pipx upgrade` or `pipx reinstall`.** Back them up first, or prefer the `git clone` installation above.

---

## Language

BSMB speaks French and English. By default it follows the language of your system. To change it:

- in the menu: **3. Settings** > **L. Language** (applied immediately);
- on the command line: `python bsmb.py --lang en` (or `fr`, or `auto`), which takes precedence over the setting.

The choice is stored in `config.json` (`"language": "en"`; an empty value means automatic). To add or fix a translation, see [lang/README.md](lang/README.md) (in French).

---

## First use

When started, BSMB shows a simple menu:

```
======================================================================
=                    BSMB - BSKY SAVE MY BOOKMARKS                   =
======================================================================
  Account: not connected | Media: none

  1. My account     - Sign-in and online bookmarks
  2. Local storage  - Folder and statistics
  3. Settings       - Application settings
  4. Download       - (connect your account first)

  0. Quit
```

### Step 1 — Connect your account

Choose **1. My account** then **1. Connect my Bluesky account**.

You will need:
- Your Bluesky **handle** (e.g. `myname.bsky.social`)
- An **App Password**

**Creating an App Password:**
1. Go to [bsky.app](https://bsky.app) > **Settings** > **App Passwords**
2. Click **Add App Password**
3. Name it (e.g. "BSMB") and copy the generated password (`xxxx-xxxx-xxxx-xxxx`)

BSMB tests the connection right away. If it works, your credentials are saved locally.

### Step 2 — Synchronize

Still in **My account**, choose **1. Synchronize bookmarks**.

BSMB fetches the complete list of your bookmarks from Bluesky and tells you how many are new.

### Step 3 — Download

Go back to the main menu and choose **4. Download X new bookmarks**.

BSMB analyzes each post and automatically downloads:
- The **images** (with EXIF metadata: author, date, link)
- The **videos** (with ffmpeg metadata)
- Text-only posts as **texts**

Files are saved in `~/Downloads/BSMB/` by default.

---

## Regular use

On every run:

1. **My account** > **Synchronize** — fetches the new bookmarks
2. **Download X new bookmarks** — downloads only what is new

BSMB remembers what has already been processed thanks to its local database.

### Command line

Without the menu, for instance for a scheduled task (see [ADVANCED.md](ADVANCED.md#planification), in French):

- `python bsmb.py sync` — synchronizes the bookmarks; `python bsmb.py download [--force]` — downloads the new ones
- `python bsmb.py run --yes` — synchronizes then downloads, without asking anything
- `python bsmb.py status [--json]` — shows the account state and the counters

---

## Main menu

| Option | Description |
|--------|-------------|
| **1. My account** | Bluesky sign-in, synchronization, online vs local counters |
| **2. Local storage** | Statistics, folder size, dead links cleanup |
| **3. Settings** | Credentials, destination folder, parallel workers, advanced mode, language |
| **4. Download** | Starts downloading the new bookmarks |

---

## Features

- **Incremental download** — only the new bookmarks are processed
- **Quote posts** — the text and media of the bookmarked post are archived, then those of the post it quotes (files `…_quote…`, two levels at most)
- **Metadata** — every file carries the author, the date and the link to the original post
- **Dead link detection** — deleted posts (error 400/500) are identified and can be cleaned up
- **Parallel download** — configurable from 1 to 16 workers (default: 4)
- **Cross-platform** — Windows, macOS, Linux
- **Bilingual interface** — French and English

---

## File naming

Format: `handle_YYYYMMDD_postid_N.ext`

Example: `artist_20260110_3abc123xyz_01.jpg`

Every file can be traced back to its original post on Bluesky.

---

## FAQ

**Does my App Password still work after a restart?**
Yes. BSMB keeps your credentials (in the system keyring if `keyring` is installed, otherwise in `config.json`) and generates a new token at every launch. The App Password does not change.

**Are my already downloaded files safe?**
Yes. Resetting the database never deletes downloaded files. It only erases the tracking history.

**Can I change the download folder?**
Yes, in **Settings** > **Download folder**.

**What happens if a post is deleted?**
BSMB flags it as a "dead link". You can clean these entries up in **Local storage** > **Clean up dead links**.

**ffmpeg or exiftool are not installed?**
Media will be downloaded normally, but without embedded metadata (author, date, etc.).

**Can I use the bookmarks list with other tools?**
Yes. The `urls.txt` file is compatible with `yt-dlp -a urls.txt`, `wget -i urls.txt`, etc.

**What happens to a post that shares a link (article, YouTube, x.com…)?**
BSMB archives the post text, the link, its title, its description and the card thumbnail. The content of the linked site is not downloaded (except a Tenor GIF or a direct `.gif` / `.mp4` / `.webp` file): `yt-dlp -a urls.txt` remains usable for those cases.

---

## Security and privacy

- Your data stays **100% local** (no upload, no tracking)
- The App Password is stored in the system keyring if `keyring` is installed (`pip install -r requirements-optional.txt`), otherwise in `config.json` (local file, ignored by Git). Create an App Password **dedicated** to BSMB and revoke it if in doubt; "My account > D" removes it from this computer.
- Only HTTPS requests to the Bluesky API are made
- Never share your App Password

---

## Advanced users

If you want to use the developer mode, the manual Bearer token, or understand the technical architecture, see the [advanced guide](ADVANCED.md) (in French).

---

## Reporting a bug

Found a problem? Report it on [GitHub Issues](https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks/issues)

Please include:
- Your platform (Windows/Mac/Linux)
- The exact error (message, logs if available)
- The steps to reproduce the problem

---

## License

Personal project — free to use.
Please respect the rights of content creators.
