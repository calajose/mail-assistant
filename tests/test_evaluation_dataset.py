from datetime import datetime, timezone
from mail_assistant.classifier.service import ClassifierService
from mail_assistant.config.models import ClassifierRules, Thresholds
from mail_assistant.imap.models import EmailHeader
from mail_assistant.llm.base import LLMClassificationResult, LLMProvider
from mail_assistant.rules.base import Category
from mail_assistant.rules.engine import RuleEngine
from mail_assistant.utils.security import extract_security_signals


class EvaluatorLLM(LLMProvider):
    def __init__(self):
        self.model = "evaluator_llm"

    def classify_email(self, email, signals, body_preview=None):
        subject = email.subject.lower()
        # Simulated LLM: If subject sounds like an alert, LLM hallucinates PELIGROSO
        if "alerta" in subject or "seguridad" in subject:
            return LLMClassificationResult(
                category=Category.PELIGROSO,
                explanation="El LLM sospecha riesgo por lenguaje de seguridad/urgencia."
            )
        # If objective security risk is present (auth_failed, links, attachments), LLM classifies as PELIGROSO
        if isinstance(signals, dict) and signals.get("security", {}).get("has_objective_risk"):
            return LLMClassificationResult(
                category=Category.PELIGROSO,
                explanation="El LLM detecta amenaza de seguridad respaldada por evidencias."
            )
        if "préstamo" in subject or "resguardo" in subject:
            return LLMClassificationResult(
                category=Category.IMPORTANTE,
                explanation="Comunicación transaccional sobre servicio o préstamo."
            )
        return LLMClassificationResult(
            category=Category.DESCARTABLE,
            explanation="Correo informativo o promocional."
        )


EVALUATION_DATASET = [
    # 1. Financiera El Corte Inglés - Legítimo con alerta
    {
        "id": "EVAL_01",
        "from": '"Financiera El Corte Inglés" <noreply@mc.financieraelcorteingles.es>',
        "subject": "Alerta de seguridad.",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Se ha detectado un inicio de sesión en tu cuenta. Si no has sido tú llama al 913779779.",
        "expected_category_not": Category.PELIGROSO,
    },
    # 2. Cantook Station / eBiblio - Legítimo préstamo
    {
        "id": "EVAL_02",
        "from": '"eBiblio Andalucía" <no-reply@cantookstation.eu>',
        "subject": "Tu préstamo: Sangre de dragón (Academia Bloodwing 1)",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Recupera tu préstamo desde https://u112203269.ct.eu.sendgrid.net/ls/click",
        "expected_category_not": Category.PELIGROSO,
    },
    # 3. Loterías y Apuestas - Legítimo
    {
        "id": "EVAL_03",
        "from": "envios@loteriasyapuestas.es",
        "subject": "Tu resguardo virtual en Loterías y Apuestas",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Aquí tienes tu resguardo de compra de Lotería.",
        "expected_category_not": Category.PELIGROSO,
    },
    # 4. Movistar - Legítimo newsletter
    {
        "id": "EVAL_04",
        "from": "hola@mail.movistar.es",
        "subject": "Estrenos de esta semana. ¿Qué quieres ver?",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Descubre los nuevos estrenos de cine en Movistar Plus+.",
        "expected_category_not": Category.PELIGROSO,
    },
    # 5. Idealista - Legítimo newsletter
    {
        "id": "EVAL_05",
        "from": "idealista@mailing.idealista.com",
        "subject": "Problemas habituales al alquilar una casa",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Te contamos todo sobre el alquiler de viviendas.",
        "expected_category_not": Category.PELIGROSO,
    },
    # 6. Amazon Fresh - Legítimo
    {
        "id": "EVAL_06",
        "from": "novedades@amazon.es",
        "subject": "Amazon Fresh: descubre nuestras ofertas",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Descuentos en productos frescos esta semana.",
        "expected_category_not": Category.PELIGROSO,
    },
    # 7. Repsol Luzygas - Legítimo
    {
        "id": "EVAL_07",
        "from": "comercial@ofertas.repsolluzygas.com",
        "subject": "Abre este mail si quieres 100 €",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Promoción especial Repsol Luz y Gas.",
        "expected_category_not": Category.PELIGROSO,
    },
    # 8. Revolut - Legítimo
    {
        "id": "EVAL_08",
        "from": "no-reply@revolut.com",
        "subject": "Recibe 60 € por cada persona que traigas a Revolut",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Programa de recomendación Revolut.",
        "expected_category_not": Category.PELIGROSO,
    },
    # 9. Cloudflare - Legítimo
    {
        "id": "EVAL_09",
        "from": "em@em1.cloudflare.com",
        "subject": "Noah Kahan is coming to Cloudflare Connect",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Novedades de Cloudflare Connect 2026.",
        "expected_category_not": Category.PELIGROSO,
    },
    # 10. Instagram - Legítimo
    {
        "id": "EVAL_10",
        "from": "follow-suggestions@mail.instagram.com",
        "subject": "Explora publicaciones en tu feed",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Nuevas sugerencias en Instagram.",
        "expected_category_not": Category.PELIGROSO,
    },
    # 11. Substack - Legítimo
    {
        "id": "EVAL_11",
        "from": "no-reply@substack.com",
        "subject": "Las 5 mejores IA para crear imágenes",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Resumen semanal de artículos en Substack.",
        "expected_category_not": Category.PELIGROSO,
    },
    # 12. PcComponentes - Legítimo
    {
        "id": "EVAL_12",
        "from": "noreply@pccomponentes.com",
        "subject": "Último finde de Días Naranjas",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Grandes ofertas en PcComponentes.",
        "expected_category_not": Category.PELIGROSO,
    },
    # 13. Trade Republic - Legítimo
    {
        "id": "EVAL_13",
        "from": "email@news.traderepublic.com",
        "subject": "Invierte fácilmente en fondos indexados",
        "headers": {"Authentication-Results": "dkim=pass; spf=pass; dmarc=pass"},
        "body": "Planes de inversión en Trade Republic.",
        "expected_category_not": Category.PELIGROSO,
    },
    # --- Correos de Phishing Reales/Sintéticos ---
    # 14. Phishing Banco Santander (Auth Fail + Link Mismatch)
    {
        "id": "EVAL_14",
        "from": '"Banco Santander" <seguridad@santander-verificacion.ru>',
        "subject": "Alerta: Confirme sus credenciales bancarias",
        "headers": {"Authentication-Results": "dkim=fail; spf=fail; dmarc=fail"},
        "body": 'Confirme su cuenta aquí: <a href="http://phishing-santander.ru/login">https://bancosantander.es</a>',
        "expected_category": Category.PELIGROSO,
    },
    # 15. Phishing Correos Aviso de Paquete
    {
        "id": "EVAL_15",
        "from": "servicio@correos-paquetes-entrega.com",
        "subject": "Su paquete no ha podido ser entregado",
        "headers": {"Authentication-Results": "dkim=fail; spf=fail; dmarc=fail"},
        "body": 'Pague las tasas aquí: <a href="http://pagos-falsos.org/correos">https://correos.es</a>',
        "expected_category": Category.PELIGROSO,
    },
    # 16. Phishing Agencia Tributaria con Adjunto Peligroso
    {
        "id": "EVAL_16",
        "from": "notificaciones@agenciatributaria-gob.es",
        "subject": "Notificación urgente de inspección fiscal",
        "headers": {"Authentication-Results": "dkim=fail; spf=fail; dmarc=fail"},
        "body": "Consulte la citación en el archivo adjunto.",
        "attachments": ["notificacion_urgente.exe"],
        "expected_category": Category.PELIGROSO,
    },
    # 17. Phishing PayPal Inicio de Sesión
    {
        "id": "EVAL_17",
        "from": "service@paypal-security-update.com",
        "subject": "Su cuenta PayPal ha sido restringida",
        "headers": {"Authentication-Results": "dkim=fail; spf=fail; dmarc=fail"},
        "body": 'Restaure su acceso en <a href="http://paypal-credential-harvesting.com">https://paypal.com</a>',
        "expected_category": Category.PELIGROSO,
    },
    # 18. Phishing Microsoft Office365 Caducidad Contraseña
    {
        "id": "EVAL_18",
        "from": "admin@office365-passwords-reset.com",
        "subject": "Caducidad de contraseña de Office 365",
        "headers": {"Authentication-Results": "dkim=fail; spf=fail; dmarc=fail"},
        "body": 'Renueve su clave aquí: <a href="http://office365-fake.com">https://microsoft.com</a>',
        "expected_category": Category.PELIGROSO,
    },
    # 19. Phishing DGT Multa Pendiente con VBScript
    {
        "id": "EVAL_19",
        "from": "multas@dgt-notificaciones.org",
        "subject": "Notificación de multa no pagada DGT",
        "headers": {"Authentication-Results": "dkim=fail; spf=fail; dmarc=fail"},
        "body": "Descargue el expediente adjunto.",
        "attachments": ["expediente_dgt.vbs"],
        "expected_category": Category.PELIGROSO,
    },
    # 20. Phishing Apple ID Deshabilitado
    {
        "id": "EVAL_20",
        "from": "support@apple-id-verify.com",
        "subject": "Tu Apple ID ha sido bloqueado por seguridad",
        "headers": {"Authentication-Results": "dkim=fail; spf=fail; dmarc=fail"},
        "body": 'Verifica tu Apple ID: <a href="http://apple-phish.ru">https://appleid.apple.com</a>',
        "expected_category": Category.PELIGROSO,
    },
    # 21. Phishing Netflix
    {
        "id": "EVAL_21",
        "from": "info@netflix-billing-update.com",
        "subject": "Actualice sus datos de pago en Netflix",
        "headers": {"Authentication-Results": "dkim=fail; spf=fail; dmarc=fail"},
        "body": 'Actualice la tarjeta en <a href="http://netflix-fake-payment.org">https://netflix.com</a>',
        "expected_category": Category.PELIGROSO,
    },
]


class MockDatasetMailClient:
    def __init__(self, headers_list, body_dict):
        self._headers_list = headers_list
        self._body_dict = body_dict

    def session(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def get_unread_emails(self, limit=100, on_progress=None):
        return self._headers_list

    def get_email_body_preview(self, uid):
        return self._body_dict.get(uid, "")


def test_evaluation_dataset_precision_and_recall():
    rules_config = ClassifierRules(
        score_thresholds=Thresholds(important=60, discard=-30),
        whitelist_domains=["loteriasyapuestas.es", "cantookstation.eu"]
    )
    rule_engine = RuleEngine(rules_config)
    llm = EvaluatorLLM()

    email_headers = []
    body_dict = {}

    for idx, item in enumerate(EVALUATION_DATASET, start=1):
        uid = str(idx)
        header = EmailHeader(
            uid=uid,
            from_=item["from"],
            subject=item["subject"],
            date=datetime.now(timezone.utc),
            message_id=f"<msg_{uid}>",
            headers=item.get("headers", {}),
            flags=set()
        )
        email_headers.append(header)
        body_dict[uid] = item.get("body", "")

    mail_client = MockDatasetMailClient(email_headers, body_dict)
    service = ClassifierService(mail_client, rule_engine, llm)

    results = service.process_unread(limit=100, use_llm=True)
    res_map = {r["header"].uid: r for r in results}

    false_positives = 0
    genuine_peligroso_detected = 0
    total_genuine_peligroso = 0

    for idx, item in enumerate(EVALUATION_DATASET, start=1):
        uid = str(idx)
        res = res_map[uid]
        category = res["category"]

        if "expected_category_not" in item:
            # Must NOT be classified as PELIGROSO
            assert category != item["expected_category_not"], f"Falso positivo en {item['id']}: {item['subject']}"
            if category == Category.PELIGROSO:
                false_positives += 1

        if "expected_category" in item:
            if item["expected_category"] == Category.PELIGROSO:
                total_genuine_peligroso += 1
                if category == Category.PELIGROSO:
                    genuine_peligroso_detected += 1
                assert category == Category.PELIGROSO, f"Phishing no detectado en {item['id']}: {item['subject']}"

    assert false_positives == 0, f"Se detectaron {false_positives} falsos positivos en correos legítimos."
    recall = (genuine_peligroso_detected / total_genuine_peligroso) * 100
    assert recall >= 95.0, f"El porcentaje de detección de phishing fue {recall}%, inferior al 95% requerido."
