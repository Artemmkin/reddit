require 'sinatra'
require 'json/ext'
require 'uri'
require 'mongo'
require 'prometheus/client'
require 'rufus-scheduler'
require_relative 'helpers'

# Database connection info
COMMENT_DATABASE_HOST ||= ENV['COMMENT_DATABASE_HOST'] || '127.0.0.1'
COMMENT_DATABASE_PORT ||= ENV['COMMENT_DATABASE_PORT'] || '27017'
COMMENT_DATABASE ||= ENV['COMMENT_DATABASE'] || 'test'
DB_URL ||= "mongodb://#{COMMENT_DATABASE_HOST}:#{COMMENT_DATABASE_PORT}"

# App version and build info
VERSION ||= File.read('VERSION').strip
BUILD_INFO = File.readlines('build_info.txt')

configure do
  Mongo::Logger.logger.level = Logger::WARN
  db = Mongo::Client.new(DB_URL, database: COMMENT_DATABASE,
                                 heartbeat_frequency: 2)
  set :mongo_db, db[:comments]
  set :bind, '0.0.0.0'
  set :server, :puma
  set :logging, false
  set :mylogger, Logger.new(STDOUT)
end

# Create and register metrics
prometheus = Prometheus::Client.registry
comment_health_gauge = Prometheus::Client::Gauge.new(
  :comment_health,
  'Health status of Comment service'
)
comment_health_db_gauge = Prometheus::Client::Gauge.new(
  :comment_health_mongo_availability,
  'Check if MongoDB is available to Comment'
)
comment_count = Prometheus::Client::Counter.new(
  :comment_count,
  'A counter of new comments'
)
prometheus.register(comment_health_gauge)
prometheus.register(comment_health_db_gauge)
prometheus.register(comment_count)

# Schedule health check function
scheduler = Rufus::Scheduler.new
scheduler.every '5s' do
  check = JSON.parse(healthcheck_handler(DB_URL, VERSION))
  set_health_gauge(comment_health_gauge, check['status'])
  set_health_gauge(comment_health_db_gauge, check['dependent_services']['commentdb'])
end

before do
  env['rack.logger'] = settings.mylogger # set custom logger
end

after do
  request_id = env['HTTP_REQUEST_ID'] || 'null'
  logger.info('service=comment | event=request | ' \
              "path=#{env['REQUEST_PATH']}\n" \
              "request_id=#{request_id} | " \
              "remote_addr=#{env['REMOTE_ADDR']} | " \
              "method= #{env['REQUEST_METHOD']} | " \
              "response_status=#{response.status}")
end

# retrieve post's comments
get '/:id/comments' do
  id = obj_id(params[:id])
  begin
    posts = settings.mongo_db.find(post_id: id.to_s).to_a.to_json
  rescue StandardError => e
    log_event('error', 'find_post_comments',
              "Couldn't retrieve comments from DB. Reason: #{e.message}",
              params)
    halt 500
  else
    log_event('info', 'find_post_comments',
              'Successfully retrieved post comments from DB', params)
    posts
  end
end

# add a new comment
post '/add_comment/?' do
  begin
    prms = { post_id: params['post_id'],
             name: params['name'],
             email: params['email'],
             body: params['body'],
             created_at: params['created_at'] }
  rescue StandardError => e
    log_event('error', 'add_comment',
              "Bat input data. Reason: #{e.message}", prms)
  end
  db = settings.mongo_db
  begin
    result = db.insert_one post_id: params['post_id'], name: params['name'],
                           email: params['email'], body: params['body'],
                           created_at: params['created_at']
    db.find(_id: result.inserted_id).to_a.first.to_json
  rescue StandardError => e
    log_event('error', 'add_comment',
              "Failed to create a comment. Reason: #{e.message}", params)
    halt 500
  else
    log_event('info', 'add_comment',
              'Successfully created a new comment', params)
    comment_count.increment
  end
end

# health check endpoint
get '/healthcheck' do
  healthcheck_handler(DB_URL, VERSION)
end

get '/*' do
  halt 404, 'Page not found'
end
