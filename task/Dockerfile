FROM python:3.12.3
 
# Create the app directory
RUN mkdir /app
 
# Set the working directory inside the container
WORKDIR /app
 
# Set environment variables 
# Prevents Python from writing pyc files to disk
ENV PYTHONDONTWRITEBYTECODE=1
#Prevents Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1 
 
# Upgrade pip
RUN pip install --upgrade pip 
 
# Copy the Django project  and install dependencies
COPY requirements.txt  /app/
 
# run this command to install all dependencies 
RUN pip install --no-cache-dir -r requirements.txt
 
# Copy the Django project to the container
COPY . /app/
 
# Expose the Django port
EXPOSE 8001
 
# Run Django’s development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]






















# FROM python:3.12.3-slim

# # Create the app directory
# RUN mkdir /app
# WORKDIR /app

# # Set environment variables
# ENV PYTHONDONTWRITEBYTECODE=1
# ENV PYTHONUNBUFFERED=1
# ENV DEBIAN_FRONTEND=noninteractive

# # Install system dependencies
# RUN apt-get update && apt-get install -y \
#     gcc \
#     python3-dev \
#     libpq-dev \
#     && rm -rf /var/lib/apt/lists/*

# # Install dependencies
# COPY requirements.txt /app/
# RUN pip install --upgrade pip && \
#     pip install --no-cache-dir -r requirements.txt

# # Copy project
# COPY . /app/

# # Create staticfiles directory and set permissions
# RUN mkdir -p /app/staticfiles && \
#     chmod -R 755 /app/staticfiles

# # Temporary database config for collectstatic
# ENV DATABASE_URL="sqlite:///temp.db"

# # Collect static files
# RUN python manage.py collectstatic --noinput

# # Expose port
# EXPOSE 8001

# # Run Gunicorn
# CMD ["gunicorn", "--bind", "0.0.0.0:8001", "tasks.wsgi:application"]






