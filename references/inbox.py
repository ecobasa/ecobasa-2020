"""References sent by replying to the reference request email. Replies go to
<mailbox>+<key>@…, an IMAP mailbox that fetch_reference_replies reads; the key (from the
address, or the subject when the address lost it) finds the reference request."""

import email
import imaplib
import json
import logging
import re
from email import policy
from html import unescape
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from .reference_requests import REPLY_MARKER, find_reference_request, save_requested_reference, send_reference_received_email, shrink_photo

logger = logging.getLogger(__name__)

KEY_IN_ADDRESS = re.compile(r"\+([0-9a-f]{24})@", re.IGNORECASE)
KEY_IN_SUBJECT = re.compile(r"\[#([0-9a-f]{24})\]", re.IGNORECASE)
# Where mail apps start quoting the email being answered
QUOTE_HEADERS = [
    re.compile(r"^\s*(On|Am|Le|El)\s.+\b(wrote|schrieb|a écrit|escribió)\b", re.IGNORECASE),
    re.compile(r"^\s*-+\s*(Original Message|Ursprüngliche Nachricht|Message d'origine|Mensaje original)\s*-+", re.IGNORECASE),
    re.compile(r"^\s*(From|Von|De)\s*:\s.+@", re.IGNORECASE),
]
WRAPPED_QUOTE_START = re.compile(r"^\s*(On|Am|Le|El)\s.+(@|<)", re.IGNORECASE)
WRAPPED_QUOTE_END = re.compile(r"^\s*\S*@?\S*>?\s*(wrote|schrieb|a écrit|escribió)\s*:\s*$", re.IGNORECASE)
MAX_TEXT_LENGTH = 5000


def find_key(message):
    for header in ("Delivered-To", "X-Original-To", "To", "Cc"):
        for value in message.get_all(header, []):
            found = KEY_IN_ADDRESS.search(str(value))
            if found:
                return found.group(1).lower()
    found = KEY_IN_SUBJECT.search(str(message.get("Subject", "")))
    return found.group(1).lower() if found else None


def _html_to_text(html):
    html = re.sub(r"(?is)<(script|style|blockquote).*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", html)
    return unescape(re.sub(r"<[^>]+>", "", html))


def reply_text(body):
    """The reply alone: no quoted email, no signature, no marker."""
    lines = []
    for line in body.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if REPLY_MARKER in line or stripped.startswith(">") or stripped == "--":
            break
        if any(pattern.match(line) for pattern in QUOTE_HEADERS):
            break
        lines.append(line.rstrip())
    # A quote header can wrap ("On Mon, … Ann <ann@…>\nwrote:"), so its halves weren't
    # recognised: drop them from the end
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and WRAPPED_QUOTE_END.match(lines[-1]):
        lines.pop()
    if lines and WRAPPED_QUOTE_START.match(lines[-1]):
        lines.pop()
    return "\n".join(lines).strip()[:MAX_TEXT_LENGTH]


def parse_reply(message):
    """(key, text, photo) from a reply; photo is the first image attached, or None."""
    body = message.get_body(preferencelist=("plain", "html"))
    text = ""
    if body is not None:
        content = body.get_content()
        text = reply_text(content if body.get_content_type() == "text/plain" else _html_to_text(content))
    photo = None
    for part in message.iter_attachments():
        if part.get_content_maintype() == "image":
            photo = part.get_content()
            break
    return find_key(message), text, photo


def handle_reply(raw_bytes):
    """Save the reference from one raw reply. Returns it, or None if the reply couldn't be
    matched to a reference request or had no text."""
    message = email.message_from_bytes(raw_bytes, policy=policy.default)
    # Never answer auto-replies ("out of office"), so two robots can't write to each other
    if message.get("Auto-Submitted", "no").lower() != "no" or message.get("X-Autoreply"):
        return None
    key, text, photo_bytes = parse_reply(message)
    reference_request = find_reference_request(key) if key else None
    if reference_request is None or not text:
        logger.info("Reference reply not saved (key=%s, has text=%s)", key, bool(text))
        return None
    photo = None
    if photo_bytes:
        try:
            photo = shrink_photo(ContentFile(photo_bytes))
        except ValueError:
            logger.info("Reference reply %s: attachment is not a readable image", key)
    reference = save_requested_reference(reference_request, text=text, photo=photo)
    if reference is not None:
        send_reference_received_email(reference_request)
    return reference


def _save_reply(raw_bytes, label):
    try:
        with transaction.atomic():
            return handle_reply(raw_bytes) is not None
    except Exception:  # pylint: disable=broad-except
        logger.exception("Reference reply %s could not be saved", label)
        return False


def fetch_replies():
    """Read unseen replies from the reference mailbox and save them. Each message is marked
    seen once handled, so a failing one is not retried forever. Returns how many
    references were saved."""
    if settings.REFERENCE_MAILPIT_URL:
        return fetch_replies_from_mailpit(settings.REFERENCE_MAILPIT_URL)
    if not settings.REFERENCE_IMAP_HOST:
        return 0
    saved = 0
    with imaplib.IMAP4_SSL(settings.REFERENCE_IMAP_HOST) as imap:
        imap.login(settings.REFERENCE_IMAP_USER, settings.REFERENCE_IMAP_PASSWORD)
        imap.select(settings.REFERENCE_IMAP_FOLDER)
        _status, data = imap.search(None, "UNSEEN")
        for number in data[0].split():
            _status, parts = imap.fetch(number, "(RFC822)")
            if _save_reply(parts[0][1], number):
                saved += 1
            imap.store(number, "+FLAGS", "\\Seen")
    return saved


def _mailpit(base_url, path, data=None, method="GET"):
    body = json.dumps(data).encode() if data is not None else None
    request = Request(base_url.rstrip("/") + path, data=body, method=method,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=10) as response:
        return response.read()


def fetch_replies_from_mailpit(base_url):
    """Development: Mailpit catches all mail, so it stands in for the mailbox. Only unread
    messages sent to the reply address count; the requests themselves sit there too."""
    local = settings.REFERENCE_REPLY_ADDRESS.partition("@")[0]
    query = f"is:unread to:{local}+"
    found = json.loads(_mailpit(base_url, f"/api/v1/search?query={quote(query)}&limit=200"))
    saved = 0
    for summary in found.get("messages", []):
        if _save_reply(_mailpit(base_url, f"/api/v1/message/{summary['ID']}/raw"), summary["ID"]):
            saved += 1
        _mailpit(base_url, "/api/v1/messages", {"IDs": [summary["ID"]], "Read": True}, method="PUT")
    return saved
