#!/bin/bash

# Define the port
PORT=8001

# Kill any process using the port
echo "Killing any process running on port $PORT..."
lsof -ti:$PORT | xargs kill -9 2>/dev/null || echo "No process found on port $PORT."

# Run the Python server on the specified port
echo "Starting server.py on port $PORT..."
python server.py --port $PORT
