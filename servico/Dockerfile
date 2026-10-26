# Imagem da API (somente produção): só as dependências que a API usa, sem pytest, ruff nem Databricks.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

# O uv instala as dependências exatamente como estão no uv.lock.
RUN pip install --no-cache-dir uv==0.11.7

WORKDIR /app

# 1) Dependências primeiro: esta camada só é refeita quando o pyproject.toml ou o uv.lock mudam.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Depois o código da API.
COPY app ./app

# A API não precisa de privilégios: roda com um usuário comum.
RUN useradd --system --no-create-home api
USER api

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# /pronto também confere o banco: o contêiner só fica "healthy" se a API consegue consultá-lo.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/pronto', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
