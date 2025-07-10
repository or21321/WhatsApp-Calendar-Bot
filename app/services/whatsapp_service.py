import requests
import json
import os

class WhatsAppService:
    def __init__(self):
        self.access_token = os.getenv('WHATSAPP_ACCESS_TOKEN')
        self.phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
        self.api_url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages"

    def send_message(self, to_phone_number, message_text):
        """Send a text message via WhatsApp Business API"""

        if not self.access_token or not self.phone_number_id:
            print("Missing WhatsApp credentials")
            return False

        # Debug the token and phone number ID
        print(f"DEBUG: Using access token: {self.access_token[:20]}...")
        print(f"DEBUG: Using phone number ID: {self.phone_number_id}")
        print(f"DEBUG: API URL: {self.api_url}")

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }

        # Debug headers
        print(f"DEBUG: Authorization header: Bearer {self.access_token[:20]}...")

        data = {
            "messaging_product": "whatsapp",
            "to": to_phone_number,
            "type": "text",
            "text": {
                "body": message_text
            }
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=data
            )

            print(f"WhatsApp API Response: {response.status_code}")
            print(f"Response body: {response.text}")

            if response.status_code == 200:
                response_data = response.json()
                print(f"Message ID: {response_data.get('messages', [{}])[0].get('id', 'N/A')}")
                print(f"Message sent successfully to {to_phone_number}")
                return True
            else:
                print(f"Failed to send message: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"Error sending message: {e}")
            return False

    def test_send_message(self, to_phone_number):
        """Send a test message to verify API is working"""
        test_message = "🎉 Hello from your WhatsApp Calendar Bot! Type 'help' to see available commands."
        return self.send_message(to_phone_number, test_message)