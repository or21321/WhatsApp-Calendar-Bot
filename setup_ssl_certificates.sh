#!/bin/bash
# Script to set up initial SSL certificates with Let's Encrypt

# Make sure to replace 'your-domain.com' with your actual domain
# and 'your-email@example.com' with your email address

# Create required directories
mkdir -p ./nginx/certbot/conf
mkdir -p ./nginx/certbot/www

# Stop any existing containers
docker compose -f docker-compose.prod.yml down

# Start nginx for certificate initialization
docker compose -f docker-compose.prod.yml up -d nginx

# Wait for nginx to start
sleep 5

# Get SSL certificate
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email \
  -d your-domain.com \
  -d www.your-domain.com

# Restart nginx to apply SSL configuration
docker compose -f docker-compose.prod.yml restart nginx

# Create .htpasswd file for Flower dashboard
echo "Creating .htpasswd file for Flower dashboard..."
mkdir -p ./nginx
docker run --rm httpd:alpine htpasswd -nb admin secure_password > ./nginx/.htpasswd

echo "SSL certificates installed. Now you can start all services:"
echo "docker compose -f docker-compose.prod.yml up -d"