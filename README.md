# ComicStreamer

## SPECIAL BRANCH: series-volume

This branch modifies the `/entities/series` api call to return version specific series names. This is to compensate 
for the lack of differentiation in reading apps like ChunkyReader. The series names will come back appended with " - vX"
where X is the defined volume. Example:

```json
{
  "series": [
        "Batman - v6",
        "Batman - v7",
        "Batman - v8"
  ]
}
```

Also the `/comiclist` endpoint has been modified to accept series in this format to query for a series by volume. 
For example `/comiclist?series=Batman - v6` will return only issues in Batman volume 6 while 
`/comiclist?series=Batman` will still return all volumes of Batman.

## Work on this fork

### March 16 2021

### March 2 2019

- Ported to Python 3, since Python 2 will not be maintaned past 2020

### September 5 2015

- added webroot option to configuration, useful for proxy pass configurations (issue #24)
- little unrar automation: after pip installation, run `paver libunrar' to automatically fetch compile and install the unrar library.
- now the scanning component ignores hidden (dot) files (issue #26)
- added new logo from blindpet (issue #27)
- upgraded to latest releases of various dependent packages

### April 5 2015

- refactoring database access in a Library object (see library branch)
- fulltext indexing and faceting support using whoosh (see whoosh branch)
- mobile optimized user interface based on angularjs and bootstrap. Designed to work with the new search api with facet support

All of these features are **experimental** and still unfinished.

-----

## Introduction

ComicStreamer is a media server app for sharing a library of comic files via a simple REST API to client applications. It allows for searching for comics based on a rich set of metadata including fields like series name, title, publisher story arcs, characters, and creator credits. Client applications may access comics by entire archive file, or by fetching page images, one at a time.

A web interface is available for searching and viewing comics files, and also for configuration, log viewing, and some control operations.

It's best used on libraries that have been tagged internally with tools like [ComicTagger](http://code.google.com/p/comictagger/) or [ComicRack](http://comicrack.cyolito.com/). However, even without tags, it will try to parse out some information from the filename (usually series, issue number, and publication year).

ComicStreamer is very early ALPHA stages, and may be very flakey, eating up memory and CPU cycles. In particular, with very large datasets, filters on the sub-lists (characters, credits, etc. ) can be slow.

If you have web development or graphic design skills, and would like to help out, please contact me at comictagger@gmail.com. In particular, ComicStreamer needs a new logo!

[Chunky Comic Reader](http://chunkyreader.com/) for iPad has added experimental ComicStreamer support. Pro upgrade required, but it's well worth it for the other features you get.  Check it out!  If you are comic reader developer (any platform), and would like to add CS support,
please contact me if you need any special support or features.

-----

## Old Compiled Package Downloads

**[Windows and Mac OS X](https://googledrive.com/host/0Bw4IursaqWhhbDFzUENfSTAwckE/)**

-----

## Requirements (for running from source)

- Python 3.5 or later
- Extra Python modules installed via pip (```python3 -m pip install -r requirements.txt```)
- Optionally, pybonjour, for automatic server discovery

-----

## Installation

For source, just unzip somewhere.  For the binary packages, it's the usual drill for that platform.
(No setup.py yet, sorry)

Settings, database, and logs are kept in the user folder:

- On Linux: "~/.ComicStreamer"
- On Mac OS: "~/Library/Application Support/ComicStreamer"
- On Windows:  "%APPDATA%\ComicStreamer"

-----

## Running

From the source, just run "comicstreamer" in the base folder (on windows you may want to rename it comicstreamer.py).

For the binary builds, run from the installed app icon.  There should be no taskbar/dock presence, but an icon should appear in the system tray (windows), or status menu (mac).

A web browser should automatically open to [http://localhost:32500"](http://localhost:32500").  On your first run, use the "config" page to set the comic folders, and the "control" page to restart the server.  It will start scanning, and all comics in the given folders and sub folders will be added to database.

Some tips:

- Use "--help" option to list command-line options
- Use the "--reset" option (CLI) or control page "Rebuild Database" to wipe the database if you're having problems.

## Using venv

### Prerequisites

#### Debian and derivates

The following packages have to be installed:

- python3
- python3-dev
- python3-venv
- libavahi-compat-libdnssd1
- libjpeg-dev
- libpng-dev
- zlib1g-dev
- libwebp-dev

For example:

```bash
apt install python3 python3-dev python3-venv libavahi-compat-libdnssd1
apt install libjpeg-dev libpng-dev zlib1g-dev libwebp-dev
```

#### Arch Linux

The following packages have to be installed:

```bash
sudo pacman -S --needed make gcc libwebp python3 unzip wget
```

After installing and configuring ComicStreamer, the following packages can be removed:

```bash
sudo pacman -Rs gcc binutils libmpc wget gc guile libatomic_ops libtool make
```

#### MacOS

The following packages have to be installed:

- python3
- jpeg
- libpng
- webp

```bash
brew install python jpeg libpng webp
```

#### Windows

The following software has to be installed:

- python 3
- Bonjour (optional)

### Manual Installation (Linux and MacOS)

Create and activate venv:

```bash
python3 -m venv /opt/comicstreamer
source /opt/comicstreamer/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install --upgrade setuptools
python3 -m pip install wheel
```

Download ComicStreamer and install needed modules and libraries:

```bash
cd /opt/comicstreamer/
curl -OL https://github.com/kounch/ComicStreamer/archive/master.zip
unzip master.zip
rm master.zip
mv ComicStreamer-master master
cd master
python3 -m pip install -r requirements.txt
python3 -m paver libunrar
```

Optionally, install extra module:

```bash
python3 -m pip install https://github.com/kounch/pybonjour-python3/releases/download/1.1.3/pybonjour-1.1.3.tar.gz
```

Test everything is ok, with an execution from shell:

```bash
/opt/comicstreamer/bin/python3 /opt/comicstreamer/master/comicstreamer --nobrowser --user-dir /opt/comicstreamer/.ComicStreamer
```

### Manual Installation (Windows)

Launch a ```cmd``` Window, then create and activate venv:

```bat
py -3 -m venv comicstreamer
comicstreamer\Scripts\activate.bat
python -m pip install --upgrade pip setuptools
python -m pip install wheel
```

Download ComicStreamer and install needed modules and libraries:

```bat
cd comicstreamer
%windir%\explorer.exe https://github.com/kounch/ComicStreamer/archive/master.zip
```

Decompress the ZIP file inside the comicstreamer folder and rename to ```master```

```bat
cd master
python -m pip install -r requirements.txt
python -m paver libunrar
```

Follow the instructions to copy UnRAR DLL to ```libunrar.so```.

Optionally, if you have installed Bonjour, install extra module:

```bat
python -m pip install https://github.com/kounch/pybonjour-python3/releases/download/1.1.3/pybonjour-1.1.3.tar.gz
```

Test everything is ok, with an execution from cmd:

```bat
python comicstreamer
```

### systemd service (Linux)

You can create a systemd service. For example, create the file ```/etc/systemd/system/comicstreamer.service```

```ini
[Unit]
Description=ComicStreamer Service
Requires=network.target local-fs.target remote-fs.target
After=network.target local-fs.target remote-fs.target

[Service]
Restart=always
RestartSec=120
ExecStart=/opt/comicstreamer/bin/python3 /opt/comicstreamer/master/comicstreamer --nobrowser --user-dir /opt/comicstreamer/.ComicStreamer
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
```
