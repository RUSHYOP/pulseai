# Use a specific version of the official Python slim image for reproducibility
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Copy only the requirements file first to leverage Docker's layer cache
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application, including the model and source code
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the Uvicorn server when the container starts
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]