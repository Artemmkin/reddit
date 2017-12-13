def obj_id(val)
  begin
    BSON::ObjectId.from_string(val)
  rescue BSON::ObjectId::Invalid
    nil
  end
end

def document_by_id(id)
  id = obj_id(id) if String === id
  if id.nil?
    {}.to_json
  else
    document = settings.mongo_db.find(_id: id).to_a.first
    (document || {}).to_json
  end
end

def healthcheck_handler(db_url, version)
  begin
    commentdb_test = Mongo::Client.new(db_url,
                                       server_selection_timeout: 2)
    commentdb_test.database_names
    commentdb_test.close
  rescue StandardError
    commentdb_status = 0
  else
    commentdb_status = 1
  end

  status = commentdb_status
  healthcheck = {
    status: status,
    dependent_services: {
      commentdb: commentdb_status
    },
    version: version
  }

  healthcheck.to_json
end

def set_health_gauge(metric, value)
  metric.set(
    {
      version: VERSION,
      commit_hash: BUILD_INFO[0].strip,
      branch: BUILD_INFO[1].strip
    },
    value
  )
end

def log_event(type, name, message, params = '{}')
  case type
  when 'error'
    logger.error('service=comment | ' \
                 "event=#{name} | " \
                 "request_id=#{request.env['HTTP_REQUEST_ID']}\n" \
                 "message=\'#{message}\'\n" \
                 "params: #{params.to_json}")
  when 'info'
    logger.info('service=comment | ' \
                 "event=#{name} | " \
                 "request_id=#{request.env['HTTP_REQUEST_ID']}\n" \
                 "message=\'#{message}\'\n" \
                 "params: #{params.to_json}")
  when 'warning'
    logger.warn('service=comment | ' \
                 "event=#{name} | " \
                 "request_id=#{request.env['HTTP_REQUEST_ID']}\n" \
                 "message=\'#{message}\'\n" \
                 "params: #{params.to_json}")
  end
end
