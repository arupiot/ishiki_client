

# build the base image
docker buildx build -f Dockerfile_base --platform linux/amd64,linux/arm64,linux/arm/v7,linux/arm/v6 -t arupiot/ishiki_client_base:latest --push .
