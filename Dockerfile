ARG ARCH

FROM ${ARCH}/python:3.8-alpine

WORKDIR /var

COPY requirements.txt /var/requirements.txt
RUN pip install -r /var/requirements.txt

COPY main.py /var/main.py

ENTRYPOINT ["python3", "main.py"]
