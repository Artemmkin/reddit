require 'bundler/setup'
require 'rack'
require 'prometheus/middleware/collector'
require 'prometheus/middleware/exporter'
require_relative 'ui_app'
require_relative 'middleware'
require 'zipkin-tracer'

# https://github.com/openzipkin/zipkin-ruby#sending-traces-on-incoming-requests
zipkin_config = {
    service_name: 'ui_app',
    service_port: 9292,
    sample_rate: 1,
    sampled_as_boolean: false,
    log_tracing: true,
    json_api_host: 'http://zipkin:9411/api/v1/spans'
}

use ZipkinTracer::RackHandler, zipkin_config

use Metrics
use Rack::Deflater, if: ->(_, _, _, body) { body.any? && body[0].length > 512 }
use Prometheus::Middleware::Collector
use Prometheus::Middleware::Exporter

run Sinatra::Application
