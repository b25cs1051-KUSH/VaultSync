FROM python:3.13-slim

WORKDIR /app
COPY server.py /app/server.py

RUN useradd --create-home --uid 10001 pocketful
USER pocketful

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "/app/server.py"]
