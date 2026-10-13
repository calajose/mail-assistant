from dataclasses import dataclass, field
from email.utils import parseaddr
from html.parser import HTMLParser
import re
from urllib.parse import urlparse

DANGEROUS_EXTENSIONS = {
    ".exe", ".scr", ".bat", ".cmd", ".vbs", ".js", ".iso", ".jar", ".ps1"
}


class _HTMLLinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []  # (href, text)
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs_dict = dict(attrs)
            self._current_href = attrs_dict.get("href")
            self._current_text = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._current_href is not None:
            text = "".join(self._current_text).strip()
            self.links.append((self._current_href, text))
            self._current_href = None
            self._current_text = []


def _extract_domain(email_address: str | None) -> str:
    if not email_address or "@" not in email_address:
        return ""
    return email_address.rsplit("@", 1)[1].strip().lower()


def _normalize_address(raw_from: str | None) -> str:
    if not raw_from:
        return ""
    _, address = parseaddr(raw_from)
    return (address or "").strip().lower()


@dataclass
class SecuritySignals:
    spf_status: str = "unknown"
    dkim_status: str = "unknown"
    dmarc_status: str = "unknown"
    from_address: str = ""
    from_domain: str = ""
    reply_to_address: str | None = None
    reply_to_domain: str | None = None
    sender_discrepancy: bool = False
    suspicious_links: list[str] = field(default_factory=list)
    dangerous_attachments: list[str] = field(default_factory=list)

    @property
    def auth_passed(self) -> bool:
        has_pass = self.spf_status == "pass" or self.dkim_status == "pass"
        no_fail = self.dmarc_status != "fail" and self.spf_status != "fail"
        return has_pass and no_fail

    @property
    def auth_failed(self) -> bool:
        if self.dmarc_status == "fail":
            return True
        if self.spf_status == "fail" and self.dkim_status in ("fail", "none", "unknown"):
            return True
        if self.dkim_status == "fail" and self.spf_status in ("fail", "none", "unknown"):
            return True
        return False

    @property
    def has_objective_risk(self) -> bool:
        if self.auth_failed:
            return True
        if self.suspicious_links:
            return True
        if self.dangerous_attachments:
            return True
        if self.sender_discrepancy and not self.auth_passed:
            return True
        return False

    def to_summary_dict(self) -> dict:
        return {
            "spf": self.spf_status,
            "dkim": self.dkim_status,
            "dmarc": self.dmarc_status,
            "auth_passed": self.auth_passed,
            "auth_failed": self.auth_failed,
            "from": self.from_address,
            "reply_to": self.reply_to_address,
            "sender_discrepancy": self.sender_discrepancy,
            "suspicious_links": self.suspicious_links,
            "dangerous_attachments": self.dangerous_attachments,
            "has_objective_risk": self.has_objective_risk,
        }

    def to_prompt_text(self) -> str:
        lines = [
            f"- Autenticacion remitente: SPF={self.spf_status}, DKIM={self.dkim_status}, DMARC={self.dmarc_status}",
            f"- Coincidencia remitente/respuesta: {'DISCREPANCIA SOSPECHOSA' if self.sender_discrepancy else 'OK'}",
            f"- Enlaces sospechosos detectados: {', '.join(self.suspicious_links) if self.suspicious_links else 'Ninguno'}",
            f"- Adjuntos de riesgo: {', '.join(self.dangerous_attachments) if self.dangerous_attachments else 'Ninguno'}",
        ]
        return "\n".join(lines)


def parse_auth_headers(headers: dict[str, str | list[str]]) -> tuple[str, str, str]:
    spf_status = "unknown"
    dkim_status = "unknown"
    dmarc_status = "unknown"

    # Convert headers to dict with lowercase keys and list/string values
    normalized_headers: dict[str, list[str]] = {}
    for k, v in (headers or {}).items():
        key = k.lower()
        if isinstance(v, (list, tuple)):
            normalized_headers[key] = [str(item) for item in v]
        else:
            normalized_headers[key] = [str(v)]

    # 1. Received-SPF header
    received_spf = " ".join(normalized_headers.get("received-spf", [])).lower()
    if received_spf:
        if received_spf.startswith("pass") or "spf=pass" in received_spf:
            spf_status = "pass"
        elif received_spf.startswith("fail") or "spf=fail" in received_spf:
            spf_status = "fail"
        elif "softfail" in received_spf:
            spf_status = "softfail"
        elif "neutral" in received_spf:
            spf_status = "neutral"
        elif "none" in received_spf:
            spf_status = "none"

    # 2. Authentication-Results header
    auth_results = " ".join(normalized_headers.get("authentication-results", [])).lower()
    if auth_results:
        # Check SPF in auth_results if not already pass
        if spf_status != "pass":
            if re.search(r"\bspf=pass\b", auth_results):
                spf_status = "pass"
            elif re.search(r"\bspf=fail\b", auth_results):
                spf_status = "fail"
            elif re.search(r"\bspf=softfail\b", auth_results):
                spf_status = "softfail"
            elif re.search(r"\bspf=none\b", auth_results):
                spf_status = "none"

        # Check DKIM
        if re.search(r"\bdkim=pass\b", auth_results):
            dkim_status = "pass"
        elif re.search(r"\bdkim=fail\b", auth_results):
            dkim_status = "fail"
        elif re.search(r"\bdkim=none\b", auth_results):
            dkim_status = "none"

        # Check DMARC
        if re.search(r"\bdmarc=pass\b", auth_results):
            dmarc_status = "pass"
        elif re.search(r"\bdmarc=fail\b", auth_results):
            dmarc_status = "fail"
        elif re.search(r"\bdmarc=none\b", auth_results):
            dmarc_status = "none"

    # Fallback if dkim-signature header exists but auth_results didn't mention DKIM
    if dkim_status == "unknown" and "dkim-signature" in normalized_headers:
        dkim_status = "none"

    return spf_status, dkim_status, dmarc_status


def find_suspicious_links(body_text: str | None) -> list[str]:
    if not body_text:
        return []

    suspicious = []

    # 1. Parse HTML links if present
    parser = _HTMLLinkExtractor()
    try:
        parser.feed(body_text)
        for href, text in parser.links:
            if not href or not href.startswith(("http://", "https://")):
                continue
            text_clean = text.strip()
            # If text visible is a domain or URL like paypal.com or https://banco.es
            text_domain_match = re.search(r"\b([a-z0-9-]+\.[a-z]{2,})\b", text_clean, re.I)
            if text_domain_match:
                claimed_domain = text_domain_match.group(1).lower()
                dest_domain = urlparse(href).netloc.lower()
                # Remove port if present
                if ":" in dest_domain:
                    dest_domain = dest_domain.split(":", 1)[0]
                if claimed_domain and dest_domain and not dest_domain.endswith("." + claimed_domain) and dest_domain != claimed_domain:
                    # Ignore if claimed is generic or dest is standard web host unless clearly mismatched
                    if not claimed_domain.endswith(dest_domain):
                        suspicious.append(f"Texto '{text_clean}' apunta a dominio distinto '{dest_domain}' ({href})")
    except Exception:
        pass

    # 2. Parse Markdown links [text](url)
    md_links = re.findall(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", body_text)
    for text, href in md_links:
        text_domain_match = re.search(r"\b([a-z0-9-]+\.[a-z]{2,})\b", text, re.I)
        if text_domain_match:
            claimed_domain = text_domain_match.group(1).lower()
            dest_domain = urlparse(href).netloc.lower()
            if ":" in dest_domain:
                dest_domain = dest_domain.split(":", 1)[0]
            if claimed_domain and dest_domain and not dest_domain.endswith("." + claimed_domain) and dest_domain != claimed_domain:
                entry = f"Texto '{text}' apunta a dominio distinto '{dest_domain}' ({href})"
                if entry not in suspicious:
                    suspicious.append(entry)

    return suspicious


def find_dangerous_attachments(attachment_names: list[str] | None) -> list[str]:
    if not attachment_names:
        return []

    dangerous = []
    for name in attachment_names:
        if not name:
            continue
        lower_name = name.lower().strip()
        for ext in DANGEROUS_EXTENSIONS:
            if lower_name.endswith(ext):
                dangerous.append(name)
                break
    return dangerous


def extract_security_signals(
    headers: dict[str, str | list[str]] | None,
    body_text: str | None = None,
    attachment_names: list[str] | None = None,
) -> SecuritySignals:
    headers = headers or {}
    spf, dkim, dmarc = parse_auth_headers(headers)

    raw_from = ""
    for k, v in headers.items():
        if k.lower() == "from":
            raw_from = str(v[0] if isinstance(v, (list, tuple)) else v)
            break

    raw_reply_to = ""
    for k, v in headers.items():
        if k.lower() == "reply-to":
            raw_reply_to = str(v[0] if isinstance(v, (list, tuple)) else v)
            break

    from_addr = _normalize_address(raw_from)
    from_dom = _extract_domain(from_addr)

    reply_addr = _normalize_address(raw_reply_to) if raw_reply_to else None
    reply_dom = _extract_domain(reply_addr) if reply_addr else None

    sender_discrepancy = False
    if reply_dom and from_dom and reply_dom != from_dom:
        # Check if reply_dom is a subdomain of from_dom or vice versa
        is_sub = reply_dom.endswith("." + from_dom) or from_dom.endswith("." + reply_dom)
        if not is_sub:
            sender_discrepancy = True

    suspicious_links = find_suspicious_links(body_text)
    dangerous_attachments = find_dangerous_attachments(attachment_names)

    return SecuritySignals(
        spf_status=spf,
        dkim_status=dkim,
        dmarc_status=dmarc,
        from_address=from_addr,
        from_domain=from_dom,
        reply_to_address=reply_addr,
        reply_to_domain=reply_dom,
        sender_discrepancy=sender_discrepancy,
        suspicious_links=suspicious_links,
        dangerous_attachments=dangerous_attachments,
    )
