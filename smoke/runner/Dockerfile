FROM python:3.12-slim
WORKDIR /app
COPY runner/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY spark_smoke.py /app/spark_smoke.py
COPY profiles /app/profiles
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/spark_smoke.py"]
