FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
COPY .env.example .

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "bot.main"]
