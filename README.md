# Monolith application

## Deploy using Capistrano

#### Requirements for the target host:
* Ruby (>2.2.0) installed via `rvm`
* MongDB
* ports `22` and `9292` should be reachable by you

#### Steps:
1. Install required gems:
`bundle install`
2. Set env vars:
```bash
export SERVER_IP=<ip_address>   # public IP address of the target host
export REPO_NAME=<account/name> # repo name to fetch the code from, e.g. Artemmkin/reddit
export DEPLOY_USER=deploy       # username used to connect via SSH
```
3. Deploy using capistrano:
```bash
bundle exec cap production deploy:initial
```
