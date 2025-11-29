# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
# PYTHONDONTWRITEBYTECODE: Prevents Python from writing pyc files
# PYTHONUNBUFFERED: Keeps Python from buffering stdout and stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (ffmpeg is often required for audio tools)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose the port (Cloud Run defaults to 8080)
EXPOSE 8080

# Command to run the application
# We use shell expansion to use the $PORT variable provided by Cloud Run
CMD ["sh", "-c", "chainlit run app.py --host 0.0.0.0 --port ${PORT:-8080}"]