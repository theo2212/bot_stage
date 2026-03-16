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
        """Extracts text from an email message object, with HTML fallback."""
        body = ""
        html_body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        part_body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        if part_body: body += part_body
                    except: pass
                elif content_type == "text/html" and "attachment" not in content_disposition:
                    try:
                        html_body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    except: pass
        else:
            try:
                content_type = msg.get_content_type()
                payload = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                if content_type == "text/html": html_body = payload
                else: body = payload
            except: pass
            
        # Fallback to HTML if no plain text
        if not body.strip() and html_body:
            import re
            # Very basic tag stripping for the LLM
            body = re.sub(r'<[^>]+>', ' ', html_body)
            body = " ".join(body.split()) # Clean whitespace
            
        return body.strip()

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
                        
                        # Robustly decode subject
                        subject_parts = decode_header(msg.get("Subject", ""))
                        subject = ""
                        for part, encoding in subject_parts:
                            if isinstance(part, bytes):
                                subject += part.decode(encoding if encoding else "utf-8", errors="ignore")
                            else:
                                subject += str(part)
                            
                        # Robustly decode sender
                        sender_parts = decode_header(msg.get("From", ""))
                        sender = ""
                        for part, encoding in sender_parts:
                            if isinstance(part, bytes):
                                sender += part.decode(encoding if encoding else "utf-8", errors="ignore")
                            else:
                                sender += str(part)
                            
                        # Get body
                        body = self._get_text_from_email(msg)
                        
                        # Get threading headers for replies
                        message_id = msg.get("Message-ID", "")
                        references = msg.get("References", "")
                        
                        emails_data.append({
                            "id": e_id,
                            "sender": sender,
                            "subject": subject,
                            "body": body[:5000], # Cap length to save tokens
                            "message_id": message_id,
                            "references": references
                        })
                        
            mail.logout()
            return emails_data
            
        except Exception as e:
            print(f"[MailReader] Error fetching emails: {e}")
            return []

    def delete_email(self, email_id):
        """Moves the email to the Trash folder by setting the \Deleted flag."""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.username, self.password)
            mail.select("INBOX")
            mail.store(email_id, '+FLAGS', '\\Deleted')
            mail.expunge()
            mail.logout()
            return True
        except Exception as e:
            print(f"[MailReader] Error deleting email {email_id}: {e}")
            return False

    def mark_unread(self, email_id):
        """Restores the \Seen flag back to unseen, so it shows up as Unread in the user's Gmail."""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.username, self.password)
            mail.select("INBOX")
            mail.store(email_id, '-FLAGS', '\\Seen')
            mail.logout()
            return True
        except Exception as e:
            print(f"[MailReader] Error marking email {email_id} as unread: {e}")
            return False

    def create_draft_reply(self, to_email, original_subject, body_text, message_id="", references=""):
        """
        Creates a new draft reply in the user's Gmail Drafts folder.
        """
        from email.message import EmailMessage
        import time
        
        try:
            msg = EmailMessage()
            msg.set_content(body_text)
            
            # Format subject: add Re: if not present
            subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
            
            msg['Subject'] = subject
            msg['From'] = self.username
            msg['To'] = to_email
            
            # Threading headers
            if message_id:
                msg['In-Reply-To'] = message_id
                
                # Build references chain
                new_refs = references.strip() if references else ""
                if new_refs:
                    msg['References'] = f"{new_refs} {message_id}"
                else:
                    msg['References'] = message_id
            
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.username, self.password)
            
            # Gmail uses 'Brouillons' or '[Gmail]/Drafts' depending on language.
            # Try English first, then French
            draft_folder = '"[Gmail]/Drafts"'
            status, _ = mail.select(draft_folder)
            if status != "OK":
                draft_folder = '"[Gmail]/Brouillons"'
                status, _ = mail.select(draft_folder)
                
            if status == "OK":
                # \Draft flag is important
                mail.append(draft_folder, '\\Draft', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
                print(f"[MailReader] Draft successfully saved to {draft_folder}")
                mail.logout()
                return True
            else:
                print(f"[MailReader] Could not find Drafts folder. Tried Drafts and Brouillons.")
                mail.logout()
                return False
                
        except Exception as e:
            print(f"[MailReader] Error creating draft: {e}")
            return False

if __name__ == "__main__":
    reader = MailReader()
    reader.test_connection()
