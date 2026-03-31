import os
import smtplib
from typing import Optional

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv


load_dotenv()




def send_email_with_csv(
    to_email: str,
    subject: str,
    csv_file: str,
    shop_domain: str,
    filename: str = "low_stock_report.csv",
) -> None:
    """
    Send an email with CSV attachment using Zoho SMTP.

    Args:
        to_email (str): recipient email
        subject (str): email subject
        csv_file (str): CSV content as string
        shop_domain (str): shop identifier (used in email body)
        filename (str): attachment filename
    """

    sender_email = os.getenv("ZOHO_EMAIL")
    sender_password = os.getenv("ZOHO_PASSWORD")
    
    with smtplib.SMTP_SSL("smtp.zoho.com", 465, timeout=10) as server :
        server.login(sender_email, sender_password)
        server.send_message(msg)

    # --- Validation ---
    if not sender_email or not sender_password:
        raise ValueError("ZOHO_EMAIL or ZOHO_PASSWORD is missing in environment variables")

    if not to_email:
        raise ValueError("Recipient email is required")

    if not csv_file:
        raise ValueError("CSV content is empty")

    # --- Create Email ---
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject

    # Email body
    body = f"""
Hello,

Please find attached your weekly low stock report for {shop_domain}.

This report contains items that are below your configured coverage threshold.

If you have any questions, contact support@merchyapp.online.

Regards,
Merchy
"""
    msg.attach(MIMEText(body.strip(), "plain"))

    # --- Attach CSV ---
    try:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(csv_file.encode("utf-8"))
        encoders.encode_base64(part)

        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{filename}"'
        )

        msg.attach(part)

    except Exception as e:
        raise Exception(f"Failed to attach CSV file: {str(e)}")

    # --- Send Email ---
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # secure connection
            server.login(sender_email, sender_password)
            server.send_message(msg)

    except smtplib.SMTPAuthenticationError:
        raise Exception("SMTP Authentication failed. Check Zoho App Password.")

    except smtplib.SMTPException as e:
        raise Exception(f"SMTP error occurred: {str(e)}")

    except Exception as e:
        raise Exception(f"Unexpected error while sending email: {str(e)}")