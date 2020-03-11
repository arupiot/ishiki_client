
# build the image
docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7,linux/arm/v6 -t arupiot/ishiki_client:0.0.8 --push .
