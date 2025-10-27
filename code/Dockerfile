FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /app

# All environment variables in one layer
ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1 \
    AWS_REGION=us-west-2 \
    AWS_DEFAULT_REGION=us-west-2



COPY services/chatbot/requirements.txt services/chatbot/requirements.txt
# Install from requirements file
RUN uv pip install -r services/chatbot/requirements.txt




RUN uv pip install aws-opentelemetry-distro>=0.10.1


# Set AWS region environment variable

ENV AWS_REGION=us-west-2
ENV AWS_DEFAULT_REGION=us-west-2


# Signal that this is running in Docker for host binding logic
ENV DOCKER_CONTAINER=1

# Create non-root user
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 8080
EXPOSE 8000

# Copy entire project (respecting .dockerignore)
COPY . .

# Health check for container monitoring
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python3 -c "import sys; sys.exit(0)"

# Use the full module path

CMD ["opentelemetry-instrument", "python", "-m", "services.chatbot.agent"]
