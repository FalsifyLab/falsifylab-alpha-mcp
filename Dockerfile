FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir falsifylab-alpha-mcp==0.3.5

ENV PYTHONUNBUFFERED=1

CMD ["falsifylab-alpha-mcp"]
