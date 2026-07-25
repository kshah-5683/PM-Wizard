FROM python:3.12-slim

WORKDIR /code

# Copy and install dependencies
COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Create a non-root user to match Hugging Face execution environments
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy the rest of the application files with user ownership permissions
COPY --chown=user . $HOME/app

# Hugging Face Spaces exposes port 7860 by default
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
