FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy files into the container
COPY . /app

# Install any necessary dependencies
# (No additional dependencies for this simple example)

# Expose the port for the app
EXPOSE 8001

# Run the Python server
CMD ["python3", "server.py"]
