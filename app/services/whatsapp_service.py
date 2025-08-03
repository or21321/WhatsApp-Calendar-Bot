import requests
import json
import os
from app.services.logger import whatsapp_logger as logger

class WhatsAppService:
    def __init__(self):
        # Use only permanent system token for production
        self.access_token = os.getenv('WHATSAPP_SYSTEM_TOKEN')
        self.phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID')

        if not self.access_token:
            raise ValueError("WHATSAPP_SYSTEM_TOKEN is required for production. Please set it in your .env file.")

        if not self.phone_number_id:
            raise ValueError("WHATSAPP_PHONE_NUMBER_ID is required. Please set it in your .env file.")

        self.api_url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages"
        print("✅ Using permanent system user token")

    def send_message(self, to_phone_number, message_text):
        """Send a text message via WhatsApp Business API"""

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }

        data = {
            "messaging_product": "whatsapp",
            "to": to_phone_number,
            "type": "text",
            "text": {
                "body": message_text
            }
        }

        try:
            # Add timeout to avoid hanging requests
            response = requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=(3.05, 27)  # 3s connect timeout, 27s read timeout
            )

            print(f"WhatsApp API Response: {response.status_code}")
            logger.info(f"WhatsApp API Response: {response.status_code}")

            if response.status_code == 200:
                response_data = response.json()
                message_id = response_data.get('messages', [{}])[0].get('id', 'N/A')
                print(f"✅ Message sent successfully! ID: {message_id}")
                logger.info("Message sent successfully", {"message_id": message_id, "to": to_phone_number})
                return True
            else:
                print(f"❌ Failed to send message: {response.status_code}")
                print(f"Response: {response.text}")
                logger.error(f"Failed to send message: {response.status_code}", 
                             context={
                                 "status_code": response.status_code,
                                 "response": response.text[:200],  # Truncate long responses
                                 "to": to_phone_number
                             })
                # Check for specific error codes
                if response.status_code == 429:
                    logger.warning("Rate limit exceeded for WhatsApp API")
                return False

        except requests.Timeout as e:
            print(f"❌ Timeout sending message: {e}")
            logger.error("Timeout sending WhatsApp message", e, {"to": to_phone_number})
            return False
        except requests.ConnectionError as e:
            print(f"❌ Connection error sending message: {e}")
            logger.error("Connection error sending WhatsApp message", e, {"to": to_phone_number})
            return False
        except Exception as e:
            print(f"❌ Error sending message: {e}")
            logger.error("Error sending WhatsApp message", e, {"to": to_phone_number})
            return False

    def test_send_message(self, to_phone_number):
        """Send a test message to verify API is working"""
        test_message = "🎉 Production WhatsApp Calendar Bot is online! Type 'help' to see available commands."
        return self.send_message(to_phone_number, test_message)