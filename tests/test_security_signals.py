from mail_assistant.utils.security import (
    extract_security_signals,
    parse_auth_headers,
    find_suspicious_links,
    find_dangerous_attachments,
    SecuritySignals,
)


def test_parse_auth_headers_pass():
    headers = {
        "Authentication-Results": "mta.yahoo.com; dkim=pass header.i=@mc.financieraelcorteingles.es; spf=pass smtp.mailfrom=bounce.mc.financieraelcorteingles.es; dmarc=pass(p=REJECT)",
        "Received-SPF": "pass (domain of bounce.mc.financieraelcorteingles.es designates 161.71.67.55 as permitted sender)"
    }
    spf, dkim, dmarc = parse_auth_headers(headers)
    assert spf == "pass"
    assert dkim == "pass"
    assert dmarc == "pass"


def test_parse_auth_headers_fail():
    headers = {
        "Authentication-Results": "mta.example.com; dkim=fail header.i=@bad.com; spf=fail; dmarc=fail"
    }
    spf, dkim, dmarc = parse_auth_headers(headers)
    assert spf == "fail"
    assert dkim == "fail"
    assert dmarc == "fail"


def test_extract_security_signals_corte_ingles():
    headers = {
        "From": '"Financiera El Corte Inglés" <noreply@mc.financieraelcorteingles.es>',
        "Authentication-Results": "mta.yahoo.com; dkim=pass header.i=@mc.financieraelcorteingles.es; spf=pass smtp.mailfrom=bounce.mc.financieraelcorteingles.es; dmarc=pass(p=REJECT)",
        "Received-SPF": "pass (domain of bounce.mc.financieraelcorteingles.es designates 161.71.67.55 as permitted sender)"
    }
    signals = extract_security_signals(headers)
    assert signals.from_address == "noreply@mc.financieraelcorteingles.es"
    assert signals.from_domain == "mc.financieraelcorteingles.es"
    assert signals.auth_passed is True
    assert signals.auth_failed is False
    assert signals.has_objective_risk is False


def test_extract_security_signals_cantook():
    headers = {
        "From": '"eBiblio Andalucía" <no-reply@cantookstation.eu>',
        "Reply-To": "eBiblio Andalucía <ebiblio.ccul@juntadeandalucia.es>",
        "Authentication-Results": "mta.yahoo.com; dkim=pass header.i=@cantookstation.eu; spf=pass smtp.mailfrom=em6550.cantookstation.eu; dmarc=pass(p=NONE)"
    }
    body = "Tu reserva está disponible. Puedes recuperar el préstamo aquí: https://u112203269.ct.eu.sendgrid.net/ls/click"
    signals = extract_security_signals(headers, body_text=body)
    assert signals.from_address == "no-reply@cantookstation.eu"
    assert signals.auth_passed is True
    assert signals.has_objective_risk is False


def test_find_suspicious_links_mismatch():
    body = 'Haz clic aquí: <a href="http://phishing-site.ru">https://banco.es/login</a>'
    suspicious = find_suspicious_links(body)
    assert len(suspicious) == 1
    assert "phishing-site.ru" in suspicious[0]


def test_find_suspicious_links_valid():
    body = 'Visita nuestra web: <a href="https://elcorteingles.es/ofertas">https://elcorteingles.es</a>'
    suspicious = find_suspicious_links(body)
    assert len(suspicious) == 0


def test_find_dangerous_attachments():
    names = ["documento.pdf", "factura_marzo.exe", "imagen.png", "script.vbs"]
    dangerous = find_dangerous_attachments(names)
    assert dangerous == ["factura_marzo.exe", "script.vbs"]


def test_security_signals_prompt_text():
    signals = SecuritySignals(
        spf_status="pass",
        dkim_status="pass",
        dmarc_status="pass",
        from_address="user@domain.com",
        from_domain="domain.com",
    )
    prompt_text = signals.to_prompt_text()
    assert "SPF=pass" in prompt_text
    assert "DKIM=pass" in prompt_text
    assert "DMARC=pass" in prompt_text
