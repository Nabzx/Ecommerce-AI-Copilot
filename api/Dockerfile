# Slim rather than alpine — scikit-learn and numpy have wheels for glibc, and
# on alpine they'd have to compile from source, which turns a 30 second build
# into a very long one.
FROM python:3.12-slim

WORKDIR /app

# Requirements first, so a code change doesn't reinstall every dependency.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
