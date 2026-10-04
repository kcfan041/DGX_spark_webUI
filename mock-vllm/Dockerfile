FROM python:3.12-slim
WORKDIR /app
COPY mock_vllm.py /app/mock_vllm.py
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "/app/mock_vllm.py", "serve"]
