FROM python:3.6.0-alpine
RUN pip install flask pymongo
WORKDIR /app
ADD . /app
EXPOSE  5000
ENTRYPOINT ["python3", "post_app.py"]
