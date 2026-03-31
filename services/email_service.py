
import os
import requests
import base64


def send_email_with_csv(
    to_email: str,
    subject: str,
    csv_file: str,
    shop_domain: str,
):
    api_key = os.getenv("RESEND_API_KEY")

    if not api_key:
        raise Exception("Missing RESEND_API_KEY")

    # encode CSV
    encoded_csv = base64.b64encode(csv_file.encode()).decode()

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": "Merchy <onboarding@resend.dev>",  # default sender
            "to": [to_email],
            "subject": subject,
            "text": f"""
Weekly low stock report for {shop_domain}.

See attached CSV.
""",
            "attachments": [
                {
                    "filename": "low_stock_report.csv",
                    "content": encoded_csv,
                }
            ],
        },
    )

    if response.status_code >= 400:
        raise Exception(f"Resend error: {response.text}")



