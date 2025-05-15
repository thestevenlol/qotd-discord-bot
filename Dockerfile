FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy just the pyproject.toml and uv.lock files first to leverage Docker layer caching
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv venv
RUN uv pip install --no-deps -e .

# Copy the rest of the application
COPY . .

# Create a volume for persistent storage
VOLUME /app/data

# Set environment variable for the database location
ENV DB_PATH=/app/data/qotd.db

# Run the bot
CMD ["python", "main.py"]
