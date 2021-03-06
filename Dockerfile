FROM arupiot/ishiki_client_base:latest

COPY src /opt/ishiki/src
WORKDIR /opt/ishiki/src

# install dependencies
RUN pip3 install -r requirements.txt

# run the display command
ENTRYPOINT ["python3"]

