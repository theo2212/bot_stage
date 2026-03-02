import imaplib
import email
from email.header import decode_header
import yaml

class MailReader:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.email_config = self.config.get("email", {})
        self.username = self.email_config.get("address")
        
        # Strip spaces from app password just in case
        raw_pw = self.email_config.get("app_password", "")
        self.password = raw_pw.replace(" ", "")
        
        self.imap_server = "imap.gmail.com"

    def test_connection(self):
        """Tests the IMAP connection with the provided credentials."""
        try:
            print(f"[MailReader] Attempting to connect to {self.imap_server} for {self.username}...")
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.username, self.password)
            
            # Select inbox to be sure
            status, messages = mail.select("INBOX")
            if status == "OK":
                print(f"[MailReader] SUCCESS! Connection established. Total emails in INBOX: {messages[0].decode('utf-8')}")
                mail.logout()
                return True
            else:
                print(f"[MailReader] Connected, but failed to select INBOX. Status: {status}")
                mail.logout()
                return False
                
        except Exception as e:
            print(f"[MailReader] Connection FAILED: {e}")
            return False

    def _get_text_from_email(self, msg):
        """Extracts plain text from an email message object."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        body = part.get_payload(decode=True).decode("utf-8")
                    except:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode("utf-8")
            except:
                pass
        return body

    def get_latest_unread_emails(self, days_back=3, limit=20):
        """
        Connects via IMAP, searches for UNSEEN emails from the last few days, 
        and extracts the sender, subject, and body.
        """
        emails_data = []
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.username, self.password)
            mail.select("INBOX")
            
            import datetime
            date_filter = (datetime.date.today() - datetime.timedelta(days=days_back)).strftime("%d-%b-%Y")
            
            # Search for unread emails since the specified date
            search_query = f'(UNSEEN SINCE "{date_filter}")'
            status, messages = mail.search(None, search_query)
            
            if status != "OK":
                print("[MailReader] Failed to search emails.")
                mail.logout()
                return []
                
            email_ids = messages[0].split()
            # Process newest first, up to the limit
            for e_id in reversed(email_ids[-limit:]):
                res, msg_data = mail.fetch(e_id, '(RFC822)')
                if res != "OK":
                    continue
                    
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Decode subject
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else "utf-8", errors="ignore")
                            
                        # Decode sender
                        sender, encoding = decode_header(msg.get("From", ""))[0]
                        if isinstance(sender, bytes):
                            sender = sender.decode(encoding if encoding else "utf-8", errors="ignore")
                            
                        # Get body
                        body = self._get_text_from_email(msg)
                        
                        emails_data.append({
                            "id": e_id,
                            "sender": sender,
                            "subject": subject,
                            "body": body[:5000] # Cap length to save tokens
                        })
                        
            mail.logout()
            return emails_data
            
        except Exception as e:
            print(f"[MailReader] Error fetching emails: {e}")
            return []

if __name__ == "__main__":
    reader = MailReader()
    reader.test_connection()
