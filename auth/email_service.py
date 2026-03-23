# agata/auth/email_service.py
"""
Email Service per AGATA

Gestisce invio email transazionali (magic link, notifiche, etc.)
Supporta SMTP configurabile via environment variables.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from flask import current_app


def get_smtp_config() -> dict:
    """
    Ottiene configurazione SMTP da environment variables

    Environment variables:
        SMTP_HOST: Server SMTP (default: localhost)
        SMTP_PORT: Porta SMTP (default: 587)
        SMTP_USER: Username per autenticazione
        SMTP_PASSWORD: Password per autenticazione
        SMTP_USE_TLS: Usa TLS (default: true)
        SMTP_FROM_EMAIL: Email mittente (default: noreply@astrogen.it)
        SMTP_FROM_NAME: Nome mittente (default: AGATA)
    """
    return {
        'host': os.getenv('SMTP_HOST', 'localhost'),
        'port': int(os.getenv('SMTP_PORT', '587')),
        'user': os.getenv('SMTP_USER'),
        'password': os.getenv('SMTP_PASSWORD'),
        'use_tls': os.getenv('SMTP_USE_TLS', 'true').lower() == 'true',
        'from_email': os.getenv('SMTP_FROM_EMAIL', 'noreply@astrogen.it'),
        'from_name': os.getenv('SMTP_FROM_NAME', 'AGATA'),
    }


def send_email(to_email: str, subject: str, html_body: str, text_body: str = None) -> bool:
    """
    Invia email via SMTP

    Args:
        to_email: Destinatario
        subject: Oggetto email
        html_body: Corpo HTML
        text_body: Corpo testo (opzionale, generato da HTML se mancante)

    Returns:
        True se invio riuscito, False altrimenti
    """
    config = get_smtp_config()

    # Se SMTP non configurato, logga e simula successo in dev
    if not config['user'] or not config['password']:
        current_app.logger.warning(
            f"SMTP not configured. Would send email to {to_email}: {subject}"
        )
        # In development, logga il link invece di inviarlo
        current_app.logger.info(f"Email body preview:\n{text_body or html_body}")
        return True  # Simula successo in dev

    try:
        # Crea messaggio
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{config['from_name']} <{config['from_email']}>"
        msg['To'] = to_email

        # Corpo testo
        if not text_body:
            # Estrai testo da HTML (semplice)
            import re
            text_body = re.sub(r'<[^>]+>', '', html_body)
            text_body = re.sub(r'\s+', ' ', text_body).strip()

        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        # Connessione SMTP
        if config['use_tls']:
            server = smtplib.SMTP(config['host'], config['port'])
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(config['host'], config['port'])

        # Autenticazione
        server.login(config['user'], config['password'])

        # Invio
        server.sendmail(config['from_email'], to_email, msg.as_string())
        server.quit()

        current_app.logger.info(f"Email sent successfully to {to_email}")
        return True

    except Exception as e:
        current_app.logger.error(f"Failed to send email to {to_email}: {e}", exc_info=True)
        return False


def send_magic_link_email(to_email: str, magic_link_url: str, is_new_user: bool = False) -> bool:
    """
    Invia email con magic link per login

    Args:
        to_email: Email destinatario
        magic_link_url: URL completo del magic link
        is_new_user: True se è un nuovo utente (personalizza messaggio)

    Returns:
        True se invio riuscito
    """
    if is_new_user:
        subject = "Benvenuto su AGATA - Completa la registrazione"
        intro_text = "Benvenuto su AGATA! Clicca il pulsante qui sotto per completare la registrazione e accedere."
    else:
        subject = "Il tuo link di accesso ad AGATA"
        intro_text = "Hai richiesto un link per accedere ad AGATA. Clicca il pulsante qui sotto per effettuare il login."

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                 max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #2c3e50; margin-bottom: 10px;">AGATA</h1>
            <p style="color: #7f8c8d; font-size: 14px;">Sistema di Analisi Astronomica</p>
        </div>

        <div style="background: #f8f9fa; border-radius: 8px; padding: 30px; margin-bottom: 20px;">
            <p style="margin-top: 0;">{intro_text}</p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{magic_link_url}"
                   style="display: inline-block; background: #4285f4; color: white;
                          text-decoration: none; padding: 14px 28px; border-radius: 6px;
                          font-weight: 500; font-size: 16px;">
                    Accedi ad AGATA
                </a>
            </div>

            <p style="font-size: 14px; color: #666;">
                Questo link scade tra <strong>15 minuti</strong> e può essere usato una sola volta.
            </p>
        </div>

        <div style="font-size: 12px; color: #999; text-align: center;">
            <p>Se non hai richiesto questo link, puoi ignorare questa email.</p>
            <p style="margin-top: 20px;">
                Non riesci a cliccare il pulsante? Copia e incolla questo link nel browser:<br>
                <a href="{magic_link_url}" style="color: #4285f4; word-break: break-all;">
                    {magic_link_url}
                </a>
            </p>
        </div>

        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">

        <div style="font-size: 11px; color: #aaa; text-align: center;">
            <p>AstroGen APS - Associazione per la Promozione della Scienza</p>
        </div>
    </body>
    </html>
    """

    text_body = f"""
AGATA - Sistema di Analisi Astronomica

{intro_text}

Clicca il link qui sotto per accedere:
{magic_link_url}

Questo link scade tra 15 minuti e può essere usato una sola volta.

Se non hai richiesto questo link, puoi ignorare questa email.

---
AstroGen APS - Associazione per la Promozione della Scienza
    """

    return send_email(to_email, subject, html_body, text_body)


def send_project_assignment_email(
    to_email: str,
    analyst_name: str,
    project_code: str,
    project_title: str,
    assigned_by: str,
    project_url: str = None
) -> bool:
    """
    Invia email di notifica assegnazione progetto

    Args:
        to_email: Email dell'analista assegnato
        analyst_name: Nome dell'analista
        project_code: Codice progetto (es. AGATA-2024-001)
        project_title: Titolo/nome della stella
        assigned_by: Nome di chi ha assegnato
        project_url: URL diretto al progetto (opzionale)

    Returns:
        True se invio riuscito
    """
    import os
    base_url = os.getenv('BASE_URL', 'https://app.astrogen.it')
    if not project_url:
        project_url = f"{base_url}/agata/variable-stars"

    subject = f"Nuovo progetto assegnato: {project_code}"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                 max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #2c3e50; margin-bottom: 10px;">AGATA</h1>
            <p style="color: #7f8c8d; font-size: 14px;">Sistema di Analisi Astronomica</p>
        </div>

        <div style="background: #f8f9fa; border-radius: 8px; padding: 30px; margin-bottom: 20px;">
            <h2 style="margin-top: 0; color: #2c3e50;">Ciao {analyst_name}!</h2>

            <p>Ti è stato assegnato un nuovo progetto di analisi:</p>

            <div style="background: white; border-left: 4px solid #4285f4; padding: 15px; margin: 20px 0;">
                <p style="margin: 0 0 10px 0;"><strong>Codice:</strong> {project_code}</p>
                <p style="margin: 0 0 10px 0;"><strong>Stella:</strong> {project_title}</p>
                <p style="margin: 0;"><strong>Assegnato da:</strong> {assigned_by}</p>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{project_url}"
                   style="display: inline-block; background: #4285f4; color: white;
                          text-decoration: none; padding: 14px 28px; border-radius: 6px;
                          font-weight: 500; font-size: 16px;">
                    Vai al Progetto
                </a>
            </div>

            <p style="font-size: 14px; color: #666;">
                Accedi ad AGATA per visualizzare i dettagli del progetto e iniziare l'analisi.
            </p>
        </div>

        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">

        <div style="font-size: 11px; color: #aaa; text-align: center;">
            <p>AstroGen APS - Associazione per la Promozione della Scienza</p>
        </div>
    </body>
    </html>
    """

    text_body = f"""
AGATA - Sistema di Analisi Astronomica

Ciao {analyst_name}!

Ti è stato assegnato un nuovo progetto di analisi:

- Codice: {project_code}
- Stella: {project_title}
- Assegnato da: {assigned_by}

Accedi ad AGATA per visualizzare i dettagli del progetto e iniziare l'analisi:
{project_url}

---
AstroGen APS - Associazione per la Promozione della Scienza
    """

    return send_email(to_email, subject, html_body, text_body)
