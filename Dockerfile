FROM ruby:2.3-alpine

RUN apk add --no-cache build-base
ENV APP_HOME /app
RUN mkdir $APP_HOME
WORKDIR $APP_HOME

ADD Gemfile* $APP_HOME/
RUN bundle install

ADD . $APP_HOME
CMD ["puma"]
