import os
import prometheus_client
import time
import structlog
import traceback
import requests
from flask import Flask, request, Response, abort, logging
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.json_util import dumps
from helpers import http_healthcheck_handler, log_event
from py_zipkin.zipkin import zipkin_span, ZipkinAttrs


CONTENT_TYPE_LATEST = str('text/plain; version=0.0.4; charset=utf-8')
POST_DATABASE_HOST = os.getenv('POST_DATABASE_HOST', '127.0.0.1')
POST_DATABASE_PORT = os.getenv('POST_DATABASE_PORT', '27017')
ZIPKIN_HOST = os.getenv('ZIPKIN_HOST', 'zipkin')
ZIPKIN_PORT = os.getenv('ZIPKIN_PORT', '9411')
ZIPKIN_URL = "http://{0}:{1}/api/v1/spans".format(ZIPKIN_HOST, ZIPKIN_PORT)

log = structlog.get_logger()

app = Flask(__name__)


def init(app):
    # appication version info
    app.version = None
    with open('VERSION') as f:
        app.version = f.read().rstrip()

    # prometheus metrics
    app.post_read_db_seconds = prometheus_client.Histogram(
        'post_read_db_seconds',
        'Request DB time'
    )
    app.post_count = prometheus_client.Counter(
        'post_count',
        'A counter of new posts'
    )
    # database client connection
    app.db = MongoClient(
        POST_DATABASE_HOST,
        int(POST_DATABASE_PORT)
    ).users_post.posts


def http_transport(encoded_span):
    # The collector expects a thrift-encoded list of spans. Instead of
    # decoding and re-encoding the already thrift-encoded message, we can just
    # add header bytes that specify that what follows is a list of length 1.
    body = '\x0c\x00\x00\x00\x01' + encoded_span
    requests.post(ZIPKIN_URL, data=body,
                  headers={'Content-Type': 'application/x-thrift'})


# Prometheus endpoint
@app.route('/metrics')
def metrics():
    return Response(prometheus_client.generate_latest(),
                    mimetype=CONTENT_TYPE_LATEST)

# Retrieve information about all posts
@zipkin_span(service_name='post', span_name='db_find_all_posts')
def find_posts():
    try:
        posts = app.db.find().sort('created_at', -1)
    except Exception as e:
        log_event('error', 'find_all_posts',
                  "Failed to retrieve posts from the database. \
                   Reason: {}".format(str(e)))
        abort(500)
    else:
        log_event('info', 'find_all_posts',
                  'Successfully retrieved all posts from the database')
        return dumps(posts)


@app.route("/posts")
def posts():
    with zipkin_span(
        service_name='post',
        zipkin_attrs=ZipkinAttrs(
            trace_id=request.headers['X-B3-TraceID'],
            span_id=request.headers['X-B3-SpanID'],
            parent_span_id=request.headers['X-B3-ParentSpanID'],
            flags=request.headers['X-B3-Flags'],
            is_sampled=request.headers['X-B3-Sampled'],
        ),
        span_name='/posts',
        transport_handler=http_transport,
        port=5000,
        sample_rate=100,
    ):
        posts = find_posts()
    return posts


# Vote for a post
@app.route('/vote', methods=['POST'])
def vote():
    try:
        post_id = request.values.get('id')
        vote_type = request.values.get('type')
    except Exception as e:
        log_event('error', 'request_error',
                  "Bad input parameters. Reason: {}".format(str(e)))
        abort(400)
    try:
        post = app.db.find_one({'_id': ObjectId(post_id)})
        post['votes'] += int(vote_type)
        app.db.update_one({'_id': ObjectId(post_id)},
                          {'$set': {'votes': post['votes']}})
    except Exception as e:
        log_event('error', 'post_vote',
                  "Failed to vote for a post. Reason: {}".format(str(e)),
                  {'post_id': post_id, 'vote_type': vote_type})
        abort(500)
    else:
        log_event('info', 'post_vote', 'Successful vote',
                  {'post_id': post_id, 'vote_type': vote_type})
        return 'OK'


# Add new post
@app.route('/add_post', methods=['POST'])
def add_post():
    try:
        title = request.values.get('title')
        link = request.values.get('link')
        created_at = request.values.get('created_at')
    except Exception as e:
        log_event('error', 'request_error',
                  "Bad input parameters. Reason: {}".format(str(e)))
        abort(400)
    try:
        app.db.insert({'title': title, 'link': link,
                       'created_at': created_at, 'votes': 0})
    except Exception as e:
        log_event('error', 'post_create',
                  "Failed to create a post. Reason: {}".format(str(e)),
                  {'title': title, 'link': link})
        abort(500)
    else:
        log_event('info', 'post_create', 'Successfully created a new post',
                  {'title': title, 'link': link})
        app.post_count.inc()
        return 'OK'


# Retrieve information about a post
@zipkin_span(service_name='post', span_name='db_find_single_post')
def find_post(id):
    start_time = time.time()
    try:
        post = app.db.find_one({'_id': ObjectId(id)})
    except Exception as e:
        log_event('error', 'post_find',
                  "Failed to find the post. Reason: {}".format(str(e)),
                  request.values)
        abort(500)
    else:
        stop_time = time.time()  # + 0.3
        resp_time = stop_time - start_time
        app.post_read_db_seconds.observe(resp_time)
        log_event('info', 'post_find',
                  'Successfully found the post information',
                  {'post_id': id})
        return dumps(post)


# Find a post
@app.route('/post/<id>')
def get_post(id):
    with zipkin_span(
        service_name='post',
        zipkin_attrs=ZipkinAttrs(
            trace_id=request.headers['X-B3-TraceID'],
            span_id=request.headers['X-B3-SpanID'],
            parent_span_id=request.headers['X-B3-ParentSpanID'],
            flags=request.headers['X-B3-Flags'],
            is_sampled=request.headers['X-B3-Sampled'],
        ),
        span_name='/post/<id>',
        transport_handler=http_transport,
        port=5000,
        sample_rate=100,
    ):
        post = find_post(id)
    return post


# Health check endpoint
@app.route('/healthcheck')
def healthcheck():
    return http_healthcheck_handler(POST_DATABASE_HOST,
                                    POST_DATABASE_PORT,
                                    app.version)


# Log every request
@app.after_request
def after_request(response):
    request_id = request.headers['Request-Id'] \
        if 'Request-Id' in request.headers else None
    log.info('request',
             service='post',
             request_id=request_id,
             path=request.full_path,
             addr=request.remote_addr,
             method=request.method,
             response_status=response.status_code)
    return response


# Log Exceptions
@app.errorhandler(Exception)
def exceptions(e):
    request_id = request.headers['Request-Id'] \
        if 'Request-Id' in request.headers else None
    tb = traceback.format_exc()
    log.error('internal_error',
              service='post',
              request_id=request_id,
              path=request.full_path,
              remote_addr=request.remote_addr,
              method=request.method,
              traceback=tb)
    return 'Internal Server Error', 500


if __name__ == "__main__":
    init(app)
    logg = logging.getLogger('werkzeug')
    logg.disabled = True   # disable default logger
    # define log structure
    structlog.configure(processors=[
         structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
         structlog.stdlib.add_log_level,
         # to see indented logs in the terminal, uncomment the line below
         # structlog.processors.JSONRenderer(indent=2, sort_keys=True)
         # and comment out the one below
         structlog.processors.JSONRenderer(sort_keys=True)
     ])
    app.run(host='0.0.0.0', debug=True)
