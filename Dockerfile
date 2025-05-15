FROM python:3.12-slim

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create a volume for persistent storage
VOLUME /app/data

# Set environment variable for the database location
ENV DB_PATH=/app/data/qotd.db

# Run the bot
CMD ["python", "main.py"]
