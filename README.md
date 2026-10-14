# WebKit API
Email validation, URL preview and article extraction API. Endpoints: /health, /email/validate?email=, /url/preview?url=, /url/extract?url=&max_chars=.
Deploys to Google Cloud Run on every push to main (GitHub Actions + Workload Identity Federation).
