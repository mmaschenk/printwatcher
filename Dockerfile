FROM python:3

COPY requirements.txt /
RUN pip install -r requirements.txt

COPY watcher.py /
COPY prusalink.py /
COPY lights.py /
COPY prusargb.py /

CMD python -u /watcher.py