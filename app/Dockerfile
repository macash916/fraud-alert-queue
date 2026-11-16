# Analyst app image: Streamlit reading and writing the app schema in PostgreSQL.
FROM python:3.11-slim

WORKDIR /srv
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY .streamlit/config.toml .streamlit/config.toml
COPY app/*.py app/

# Run as an ordinary user, not root.
RUN useradd --create-home analyst
USER analyst

EXPOSE 8501
HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
