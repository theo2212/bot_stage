import re

class TextCleaner:
    @staticmethod
    def clean_description(text: str) -> str:
        """
        Strips boilerplate and noise from job descriptions to save LLM tokens.
        """
        if not text:
            return ""
            
        # 1. Normalize whitespace
        text = " ".join(text.split())
        
        # 2. Boilerplate patterns (Common legal/HR footers)
        boilerplates = [
            r"equal opportunity employer.*",
            r"don't meet every single requirement.*",
            r"we are committed to diversity.*",
            r"tous nos postes sont ouverts aux personnes en situation de handicap.*",
            r"conformément à la réglementation sur la protection des données.*",
            r"covid-19.*",
            r"vaccination.*",
            r"physical requirements.*",
            r"privacy policy.*"
        ]
        
        for pattern in boilerplates:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
            
        # 3. Truncate if still too long (safety cap for LLM)
        return text[:1500]
