"""Extract text from PDF, URL, YouTube."""
import io
import re
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from youtube_transcript_api import YouTubeTranscriptApi


def from_pdf_bytes(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((p.extract_text() or "") for p in reader.pages)


def from_url(url: str) -> str:
    r = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header"]):
        t.decompose()
    return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()


def _yt_id(url_or_id: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", url_or_id)
    return m.group(1) if m else url_or_id


def from_youtube(url_or_id: str) -> str:
    vid = _yt_id(url_or_id)
    tr = YouTubeTranscriptApi.get_transcript(vid)
    return " ".join(seg["text"] for seg in tr)
