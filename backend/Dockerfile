FROM python:3.11-slim

# Node is required for the AAR signer/verifier (tools/aar.mjs).
RUN apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# DATABASE_URL, STRIPE_*, ADMIN_API_KEY, SECRET_KEY, AINODE_*, AEGIS_SIGNING_JWK,
# RESEND_API_KEY_AEGIS are injected by Coolify at runtime (never baked in).
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
