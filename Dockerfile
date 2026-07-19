FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# .env and serviceAccountKey.json are not baked into the image — mount them at runtime:
#   docker run --env-file .env -v ./serviceAccountKey.json:/app/serviceAccountKey.json ...
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
