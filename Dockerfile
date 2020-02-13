FROM balenalib/raspberrypi3-debian:buster

RUN [ "cross-build-start" ]

RUN apt-get update && apt-get upgrade
RUN apt-get install -y --no-install-recommends apt-utils build-essential python3-dev python3-pip libssl-dev libffi-dev python3-setuptools
RUN apt-get install -y python3-pil python3-pip

RUN mkdir /opt/ishiki
COPY src /opt/ishiki/src
WORKDIR /opt/ishiki/src

# install dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# run the display command
ENTRYPOINT ["python3"]

RUN [ "cross-build-end" ]