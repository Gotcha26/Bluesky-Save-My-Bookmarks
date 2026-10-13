🇫🇷 [Version française](README.md)

# BSMB - Bsky Save My Bookmarks

Automatically save the images, videos and texts of your Bluesky bookmarks.

> The French [README](README.md) is the reference; this page is its English translation. The
> other guides ([ADVANCED.md](ADVANCED.md), [CONTRIBUTING.md](CONTRIBUTING.md),
> [DEVELOPMENT.md](DEVELOPMENT.md), [CHANGELOG.md](CHANGELOG.md)) are only available in French.

BSMB speaks French and English. By default it follows the language of your system; change it in **Settings** > **L. Language**, or with `--lang en` on the command line. To add or fix a translation, see [lang/README.md](lang/README.md) (in French).

---

## How does it work?

1. You connect your Bluesky account (once)
2. BSMB fetches the list of your bookmarks
3. It downloads the media (images, videos, texts) into a local folder
4. On every run, only the **new** bookmarks are processed

Everything is automatic. No token to copy and paste, no file to edit by hand.

---

## Installation

BSMB requires **Python 3.11 or newer**. `ffmpeg` and `exiftool` are optional: without them, media are downloaded but without embedded metadata.

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

BSMB reads and writes `config.json`, `bsmb.db`, `bookmarks.json` and `logs/` in its installation folder (the one containing `bsmb.py`), whatever the current folder. **With pipx, this folder lives inside the pipx environment: these files (credentials, history, logs) are lost on `pipx upgrade` or `pipx reinstall`.** Back them up first, or prefer the `git clone` installation above.

### System keyring (optional)

To store the App Password in the system keyring (Credential Manager, Keychain, Secret Service) instead of `config.json`: `pip install -r requirements-optional.txt` (or `pipx install ".[keyring]"`).

---

## First use

When started, BSMB shows a simple menu:

```
======================================================================
=                BSMB v3.1.0 - BSKY SAVE MY BOOKMARKS                =
======================================================================
  Account: not connected | Media: none

  1. My account     - Sign-in and online bookmarks
  2. Local storage  - Folder and statistics
  3. Settings       - Application settings

  4. Download       - (connect your account first)

  0. Quit
```

### Step 1: connect your account

Choose **1. My account** then **1. Connect my Bluesky account**.

You will need:
- Your Bluesky **handle** (e.g. `myname.bsky.social`)
- An **App Password**

**Creating an App Password:**
1. Go to [bsky.app](https://bsky.app) > **Settings** > **App Passwords**
2. Click **Add App Password**
3. Name it (e.g. "BSMB") and copy the generated password (`xxxx-xxxx-xxxx-xxxx`)

BSMB tests the connection right away. If it works, your credentials are saved locally.

### Step 2: synchronize

Still in **My account**, choose **1. Synchronize bookmarks**.

BSMB fetches the complete list of your bookmarks from Bluesky and tells you how many are new.

### Step 3: download

Go back to the main menu and choose **4. Download X new bookmarks**.

BSMB analyzes each post and automatically saves:
- the **images**, in original quality, with EXIF metadata (author, date, link, alt text);
- the **videos** (up to 10 minutes), GIFs and their subtitles, with ffmpeg metadata;
- the **text** of every post in a readable `.txt` file, together with a `.json` sidecar (the post as Bluesky provides it);
- the **link cards** (title, description, thumbnail) and, for quote posts, the quoted post.

Files are saved in `~/Downloads/BSMB/` by default, in the `images/`, `videos/` and `texts/` subfolders.

---

## Regular use

On every run:

1. **My account** > **Synchronize**: fetches the new bookmarks
2. **Download X new bookmarks**: downloads only what is new

BSMB remembers what has already been processed thanks to its local database.

### Command line

Without the menu, for instance for a scheduled task (see [ADVANCED.md](ADVANCED.md#planification), in French); an account must already be configured through the menu. With the `git clone` installation, replace `bsmb` with `python bsmb.py`:

- `bsmb sync`: synchronizes the bookmarks; `bsmb download [--force]`: downloads the new ones
- `bsmb run --yes`: synchronizes then downloads, without asking anything
- `bsmb status [--json]`: shows the account state and the counters
- `bsmb --version`: shows the version
- `bsmb --lang en ...`: sets the interface language (`fr`, `en` or `auto`)

---

## Main menu

| Option | Description |
|--------|-------------|
| **1. My account** | Bluesky sign-in, synchronization, disconnection, online and local counters |
| **2. Local storage** | Statistics, folder size, opening the folder, dead links cleanup, database reset |
| **3. Settings** | Credentials, destination folder, parallel workers, advanced mode, language |
| **4. Download** | Starts downloading the new bookmarks |

---

## Features

- **Incremental download**: only the new bookmarks are processed
- **Faithful archive**: every post gives a readable `.txt` and a `.json` sidecar (can be turned off)
- **Quote posts**: the text and media of the bookmarked post are archived, then those of the post it quotes (files `…_quote…`, two levels at most)
- **Images in original quality**, videos up to 10 minutes and 300 MB, GIFs, subtitles, link cards
- **Metadata**: every image and video carries the author, the date and the link to the original post (with ffmpeg and exiftool)
- **Dead link detection**: deleted or blocked posts are identified and can be cleaned up
- **Parallel download**: configurable from 1 to 16 workers (default: 4)
- **Usable without the menu**: subcommands and exit codes for scheduled tasks
- **Cross-platform**: Windows, macOS, Linux
- **Bilingual interface**: French and English

---

## File naming

Format: `handle_YYYYMMDD_postid_NN.ext`

Example: `artist_20260110_3abc123xyz_01.jpg`

Every file can be traced back to its original post on Bluesky. Texts and sidecars share the same base name without the index (`artist_20260110_3abc123xyz.txt` and `.json`, in `texts/`), subtitles add their language (`…_01.fr.vtt`) and the files of a quoted post contain `_quote`.

---

## FAQ

### Account and security

**Does my App Password still work after a restart?**
Yes. BSMB keeps your credentials (in the system keyring if `keyring` is installed, otherwise in `config.json`) and generates a new token at every launch. The App Password does not change.

**What is the token for?**
Only the synchronization of the bookmarks (`getBookmarks`) requires authentication: BSMB obtains a temporary token from your App Password and keeps it in memory. Downloading the posts only uses public requests. You never have to copy a token by hand (except as a last resort: see [ADVANCED.md](ADVANCED.md#méthode-2--token-bearer-manuel-secours)).

**"Token expired" or "Invalid credentials" message?**
With an App Password, BSMB renews the token itself; if the message persists, check the handle and the App Password in **Settings** > **1. Bluesky credentials**, and create the App Password again on bsky.app if needed. With a manual `Token-Bearer.txt`, you must paste a new one.

### Downloading

**How are new bookmarks handled?**
**My account** > **Synchronize**, then **Download**. Only the new posts (and those in temporary error for more than 7 days) are processed; the others are not downloaded again.

**Can I download everything again, or only a short list?**
Yes, in the advanced options (**Settings** > **4. Advanced mode**): **Force DL** reprocesses all the URLs of `urls.txt`, **Dev mode** processes them without touching the database. For a short list, edit `urls.txt` first. On the command line: `python bsmb.py download --force`. Details in [ADVANCED.md](ADVANCED.md#mode-développeur).

**What happens if a post is deleted by its author?**
BSMB flags it as a "dead link", lists it in the final report and in `logs/deleted_posts_*.txt`, and does not retry it. A blocked post is handled the same way. You can clean these entries up in **Local storage** > **Clean up dead links**.

**Are quote posts supported?**
Yes. A post that quotes another one is archived like any post, then the quoted post is archived in turn (files `…_quote…`, two levels at most). If the quoted post is deleted or blocked, a note is added to the log and the bookmark stays "ok"; if a network error prevents it from being archived, it is listed in `logs/quotes_unresolved_*.txt`.

**I have "processed" posts but few media, why?**
This is normal: a post is recorded as soon as it has been processed, even without media (text only, deleted, blocked, error). The reasons can be read in the `logs/` folder: `failed_downloads_*.txt`, `deleted_posts_*.txt`, `quotes_unresolved_*.txt`, `error_500_*.txt`, `rate_limited_*.txt`, `unknown_types_*.txt`, and `download_*.log` for the details of the session.

**Some posts are in "Failure" or "Error 500".**
Often a temporary network or server error (Bluesky). A server error 500 or a rate limit (429) is retried automatically after 7 days. A download failure (listed in `logs/failed_downloads_*.txt`), however, is not retried by itself: the post stays marked as processed. To retry it, use **Force DL** (or `python bsmb.py download --force`).

**What happens to a post that shares a link (article, YouTube, x.com…)?**
BSMB archives the post text, the link, its title, its description and the card thumbnail. The content of the linked site is not downloaded (except a Tenor GIF or a direct `.gif` / `.mp4` / `.webp` file).

**Can I use the bookmarks list with other tools?**
Yes. The `urls.txt` file holds one URL per line: it is compatible with `wget -i urls.txt` or `yt-dlp -a urls.txt` (external, optional tools). `bookmarks.json` keeps the complete answer from Bluesky.

### Storage and data

**Where is my data?**
By default in `~/Downloads/BSMB/` (`images/`, `videos/`, `texts/`). The `bsmb.db` database, `config.json`, `urls.txt`, `bookmarks.json` and `logs/` are in the BSMB installation folder.

**Can I change the download folder?**
Yes, in **Settings** > **2. Download folder**. Files already downloaded are not moved: do it by hand if you wish.

**Can I move or rename my media safely?**
Yes. The database only remembers file names, not their location. BSMB no longer "sees" moved files, but the posts stay marked as processed: nothing is downloaded again automatically (except with Force DL).

**What does the database contain?**
`bsmb.db` (SQLite) keeps the history of all processed posts (URL, author, status) and of downloaded media (type, file name). It does not contain the media themselves. It is **cumulative**: `urls.txt` reflects your current bookmarks, the database everything that has been processed, even if you have removed the bookmark since. To browse it, open it with [DB Browser for SQLite](https://sqlitebrowser.org/) (schema in [ADVANCED.md](ADVANCED.md#base-de-données-sqlite)).

**Are my already downloaded files safe?**
Yes. Resetting the database never deletes downloaded files, it only erases the tracking history.

**Should I delete my Bluesky bookmarks after downloading?**
No. They are independent of BSMB: keep them, add new ones, run BSMB from time to time, it only fetches the new ones. BSMB is your local backup.

### Installation and compatibility

**I know nothing about computers, what must I install?**
On Windows, double-click `Start.bat`: it installs Python, the libraries, ffmpeg and exiftool (5 to 10 minutes, Internet connection required). On Linux and macOS, run `./start.sh`.

**Does BSMB work without ffmpeg or exiftool?**
Yes, but without embedded metadata (author, date, alt text) in videos and images. Media are downloaded and named normally.

**Which Python version?**
Python 3.11 or newer.

**I do not see all the menu options.**
The menu adapts to your situation: **4. Download** is only active once the account is connected and the bookmarks are synchronized, and shows "Everything is up to date" when there is nothing new. The advanced options only appear in **Settings** when advanced mode is enabled.

---

## Security and privacy

- Your data stays **100% local** (no upload, no tracking)
- The App Password is stored in the system keyring if `keyring` is installed (`pip install -r requirements-optional.txt`), otherwise in `config.json` (local file, ignored by Git). Create an App Password **dedicated** to BSMB and revoke it if in doubt; "My account > D" removes it from this computer.
- `bookmarks.json` (the latest answer from Bluesky) contains the full text of your bookmarked posts: it is ignored by Git, do not publish it.
- Only HTTPS requests are made: to Bluesky (API, your account's server and CDN) and, for a post that shares a GIF, to the host of that GIF
- Never share your App Password

---

## Advanced users

For the developer mode, the manual Bearer token, scheduling, detailed configuration or the technical architecture, see the [advanced guide](ADVANCED.md) (in French). To contribute: [CONTRIBUTING.md](CONTRIBUTING.md) and [DEVELOPMENT.md](DEVELOPMENT.md). The version history is in the [CHANGELOG](CHANGELOG.md).

---

## Reporting a bug

Found a problem? Report it on [GitHub Issues](https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks/issues).

Please include:
- The output of `bsmb --version` (or `python bsmb.py --version`)
- The output of `bsmb status --json` (or `python bsmb.py status --json`): account state and counters, without any network call. Read it again before publishing it.
- Your platform (Windows/Mac/Linux) and your Python version
- The exact error (message, excerpts from `logs/` if available)
- The steps to reproduce the problem

---

## License

Personal project: free to use.
Please respect the rights of content creators.
