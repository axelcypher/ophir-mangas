"""Fetching what a user pasted a link to: a product page (link_import.py) or a picture (images.py),
and asking the bibliographic services a lookup needs (lookup.py).

The server makes these requests on a user's behalf, so they are kept to the public internet:
only http(s), only hosts that resolve to public addresses (no loopback, private network,
link-local or the like -- the app must not become a way to look into the network it runs in),
every redirect checked the same way, a size limit and a timeout.
"""

import ipaddress
import json
import socket
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = "Mozilla/5.0 (compatible; OphirMangas/1.0; +https://github.com/axelcypher/ophir-mangas)"
TIMEOUT_SECONDS = 15
MAX_REDIRECTS = 5


class FetchError(Exception):
    """A fetch that did not bring a usable answer; the message is shown to the user (German).
    `blocked`: the site refused an automatic request (bot protection, throttling), so reading the
    page in the user's own browser (the bookmarklet) is the way to go. `status`: the HTTP status of
    a refused post_json, so a caller can tell "not found" (AniList's 404 for an unknown id) from a
    service that is down."""

    def __init__(self, message, blocked=False, status=None):
        super().__init__(message)
        self.blocked = blocked
        self.status = status


def public_address(host):
    """Whether every address the host resolves to is a public one."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise FetchError("Die Adresse ist nicht erreichbar (Name unbekannt).")
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global or address.is_multicast:
            return False
    return bool(infos)


def check_url(url):
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise FetchError("Nur http- und https-Links können abgerufen werden.")
    if not public_address(parsed.hostname):
        raise FetchError("Adressen im lokalen Netz werden nicht abgerufen.")
    return parsed.geturl()


def fetch(url, max_bytes, accept="*/*", session=None):
    """(final url, content type, body bytes). Raises FetchError."""
    http = session or requests
    current = check_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        try:
            response = http.get(current, headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "de,en;q=0.8,ja;q=0.6"},
                                timeout=TIMEOUT_SECONDS, allow_redirects=False, stream=True)
        except requests.RequestException as error:
            raise FetchError(f"Die Seite antwortet nicht ({type(error).__name__}).")
        try:
            if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise FetchError("Die Seite leitet ins Leere weiter.")
                current = check_url(urljoin(current, location))
                continue
            if response.status_code == 429:
                raise FetchError("Die Seite bremst automatische Abrufe gerade aus (429). Versuch es später noch einmal, "
                                 "oder öffne sie im Browser und nutze das Lesezeichen „Zu Ophir Mangas“.", blocked=True)
            if response.status_code in (401, 403, 503):
                raise FetchError("Die Seite lässt keinen automatischen Abruf zu (Schutz vor Bots). "
                                 "Öffne sie im Browser und nutze das Lesezeichen „Zu Ophir Mangas“ oder trage die Daten von Hand ein.", blocked=True)
            if response.status_code >= 400:
                raise FetchError(f"Die Seite antwortet mit Fehler {response.status_code}.")
            return current, (response.headers.get("Content-Type") or "").split(";")[0].strip().lower(), read_body(response, max_bytes)
        finally:
            response.close()
    raise FetchError("Zu viele Weiterleitungen.")


def read_body(response, max_bytes):
    """The answer's bytes, given up on as soon as they pass max_bytes rather than after."""
    body = bytearray()
    for chunk in response.iter_content(65536):
        body.extend(chunk)
        if len(body) > max_bytes:
            raise FetchError("Die Antwort ist zu groß.")
    return bytes(body)


def post_json(url, payload, max_bytes=2 * 1024 * 1024, session=None):
    """POSTs `payload` as JSON (a GraphQL query to AniList) and returns the parsed answer, a dict.
    The same guards as fetch(), except that a redirect is refused rather than followed: an API
    that sends a POST elsewhere is not answering it, and following would repeat the body to a
    host nobody checked. Raises FetchError (with the HTTP status where there was one)."""
    http = session or requests
    target = check_url(url)
    try:
        response = http.post(target, json=payload, headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                             timeout=TIMEOUT_SECONDS, allow_redirects=False, stream=True)
    except requests.RequestException as error:
        raise FetchError(f"Der Dienst antwortet nicht ({type(error).__name__}).")
    try:
        status = response.status_code
        if response.is_redirect or status in (301, 302, 303, 307, 308):
            raise FetchError("Der Dienst leitet die Anfrage weiter; Weiterleitungen werden hier nicht verfolgt.", status=status)
        if status == 429:
            raise FetchError("Der Dienst bremst automatische Abfragen gerade aus (429). Versuch es später noch einmal.",
                             blocked=True, status=status)
        if status in (401, 403, 503):
            raise FetchError(f"Der Dienst lässt die Abfrage gerade nicht zu ({status}).", blocked=True, status=status)
        if status >= 400:
            raise FetchError(f"Der Dienst antwortet mit Fehler {status}.", status=status)
        body = read_body(response, max_bytes)
    finally:
        response.close()
    try:
        answer = json.loads(body)
    except ValueError:
        raise FetchError("Die Antwort des Dienstes ist kein lesbares JSON.")
    if not isinstance(answer, dict):
        raise FetchError("Die Antwort des Dienstes ist kein lesbares JSON.")
    return answer
