import requests


class GPTClient:
    def __init__(self, url, model):
        self.url = url
        self.model = model

    def query(self, prompt):
        """
        Send the final prompt to the local GPT (Ollama) and return response text.
        """
        try:
            payload = {
                "prompt": prompt,
                "model": self.model,
                "stream": False
            }
            resp = requests.post(self.url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            # If it's a list, might be streaming tokens
            if isinstance(data, list):
                return "".join(part.get("response", "") for part in data).strip()
            elif isinstance(data, dict):
                return data.get("response", "").strip()
            else:
                return "No valid response from local GPT."
        except Exception as e:
            print("[ERROR] GPT query failed:", e)
            return "Error: Could not reach local GPT."
